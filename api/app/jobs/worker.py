"""The worker process: claim a job, run its handler, record the outcome, repeat.

While a handler runs, a background thread keeps the job's heartbeat fresh, so a long
job is never mistaken for a stuck one. The worker also keeps its own row in
`worker_heartbeats`.
"""

import logging
import os
import socket
import threading
from datetime import timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import utcnow
from app.core.logging import context_id
from app.core.settings import Settings
from app.jobs import queue
from app.jobs.models import Job, WorkerHeartbeat
from app.jobs.registry import HANDLERS, JobContext, PermanentError

log = logging.getLogger("memoir.worker")


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def touch_worker(session: Session, wid: str, started_at) -> None:
    now = utcnow()
    stmt = insert(WorkerHeartbeat).values(
        worker_id=wid, started_at=started_at, last_seen=now
    )
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["worker_id"], set_={"last_seen": now}
        )
    )
    session.commit()


def _keep_alive(
    factory: sessionmaker, job_id: int, every: float, stop: threading.Event
):
    with factory() as session:
        while not stop.wait(every):
            queue.beat(session, job_id)


def run_one(
    session: Session, factory: sessionmaker, job: Job, settings: Settings
) -> None:
    """Run one claimed job to an outcome. Never raises: failures go on the job."""
    fn = HANDLERS.get(job.kind)
    token = context_id.set(f"job:{job.id}")
    stop = threading.Event()
    beat = threading.Thread(
        target=_keep_alive,
        args=(factory, job.id, settings.worker_heartbeat_seconds, stop),
        daemon=True,
    )
    try:
        if fn is None:
            raise PermanentError(f"no handler for job kind {job.kind!r}")
        beat.start()
        ctx = JobContext(session, job.id, job.attempts, job.max_attempts)
        result = fn(ctx, dict(job.payload))
        queue.succeed(session, job, result)
        log.info("job %s %s succeeded", job.id, job.kind)
    except Exception as exc:  # a handler's failure is the job's, never the worker's
        session.rollback()
        retry = not isinstance(exc, PermanentError)
        queue.fail(
            session,
            job,
            f"{type(exc).__name__}: {exc}",
            base_seconds=settings.job_backoff_base_seconds,
            retry=retry,
        )
        log.warning("job %s %s failed (%s)", job.id, job.kind, type(exc).__name__)
    finally:
        stop.set()
        if beat.is_alive():
            beat.join()
        context_id.reset(token)


def run(factory: sessionmaker, settings: Settings, stop: threading.Event) -> None:
    """Poll for jobs until `stop` is set."""
    wid, started = worker_id(), utcnow()
    stale = timedelta(seconds=settings.job_stale_seconds)
    log.info("worker %s started", wid)
    with factory() as session:
        last_touch = 0.0
        while not stop.is_set():
            now = utcnow().timestamp()
            if now - last_touch >= settings.worker_heartbeat_seconds:
                touch_worker(session, wid, started)
                last_touch = now
            job = queue.claim(session, wid, stale)
            if job is None:
                stop.wait(settings.worker_poll_seconds)
                continue
            run_one(session, factory, job, settings)
    log.info("worker %s stopped", wid)
