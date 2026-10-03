import threading
from datetime import timedelta

from sqlalchemy import select, update

from app.core.db import utcnow
from app.jobs import queue, worker
from app.jobs.models import Job, JobStatus, WorkerHeartbeat
from app.jobs.registry import HANDLERS, PermanentError, handler

STALE = timedelta(minutes=5)


def test_enqueue_with_the_same_idempotency_key_returns_one_job(session):
    a = queue.enqueue(session, "system.ping", {"n": 1}, idempotency_key="k1")
    b = queue.enqueue(session, "system.ping", {"n": 2}, idempotency_key="k1")
    assert a.id == b.id
    assert session.scalars(select(Job)).all() == [a]


def test_a_job_is_claimed_once_by_two_racing_workers(factory):
    with factory() as s:
        job_id = queue.enqueue(s, "system.ping").id
    barrier = threading.Barrier(2)
    claimed: list[int | None] = []

    def race(name: str) -> None:
        with factory() as s:
            barrier.wait()
            job = queue.claim(s, name, STALE)
            claimed.append(job.id if job else None)

    threads = [threading.Thread(target=race, args=(n,)) for n in ("w1", "w2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(claimed, key=lambda x: x is None) == [job_id, None]


def test_the_worker_runs_a_job_to_success(factory, settings):
    with factory() as s:
        job_id = queue.enqueue(s, "system.ping", {"hello": "world"}).id
        job = queue.claim(s, "w1", STALE)
        worker.run_one(s, factory, job, settings)
        done = s.get(Job, job_id)
        s.refresh(done)
    assert done.status == JobStatus.SUCCEEDED
    assert done.result == {"pong": {"hello": "world"}}
    assert done.progress == {"step": "pong"}
    assert done.attempts == 1


def test_a_failing_job_retries_with_backoff_and_stops_at_the_limit(factory, settings):
    calls = []

    @handler("test.always_fails")
    def always_fails(ctx, payload):
        calls.append(1)
        raise RuntimeError("boom")

    try:
        with factory() as s:
            job_id = queue.enqueue(s, "test.always_fails", max_attempts=3).id
            waits = []
            for _ in range(3):
                s.execute(update(Job).values(run_after=utcnow()))
                s.commit()
                job = queue.claim(s, "w1", STALE)
                before = utcnow()
                worker.run_one(s, factory, job, settings)
                s.refresh(job)
                waits.append(job.run_after - before)
            final = s.get(Job, job_id)
    finally:
        del HANDLERS["test.always_fails"]
    assert len(calls) == 3
    assert final.status == JobStatus.FAILED
    assert final.error == "RuntimeError: boom"
    base = settings.job_backoff_base_seconds
    assert timedelta(seconds=base) <= waits[0] < timedelta(seconds=base + 5)
    assert timedelta(seconds=2 * base) <= waits[1] < timedelta(seconds=2 * base + 5)
    assert queue.claim(s, "w1", STALE) is None


def test_backoff_doubles_and_is_capped_at_an_hour():
    assert queue.backoff(1, 30) == timedelta(seconds=30)
    assert queue.backoff(3, 30) == timedelta(seconds=120)
    assert queue.backoff(20, 30) == timedelta(hours=1)


def test_a_permanent_error_is_not_retried(factory, settings):
    @handler("test.bad_payload")
    def bad(ctx, payload):
        raise PermanentError("no such record")

    try:
        with factory() as s:
            job_id = queue.enqueue(s, "test.bad_payload").id
            worker.run_one(s, factory, queue.claim(s, "w1", STALE), settings)
            job = s.get(Job, job_id)
            s.refresh(job)
    finally:
        del HANDLERS["test.bad_payload"]
    assert (job.status, job.attempts) == (JobStatus.FAILED, 1)


def test_an_unknown_kind_fails_permanently(factory, settings):
    with factory() as s:
        job_id = queue.enqueue(s, "nobody.handles.this").id
        worker.run_one(s, factory, queue.claim(s, "w1", STALE), settings)
        job = s.get(Job, job_id)
        s.refresh(job)
    assert job.status == JobStatus.FAILED
    assert "no handler" in job.error


def test_a_stuck_job_is_reclaimed_after_its_heartbeat_lapses(session):
    job_id = queue.enqueue(session, "system.ping").id
    assert queue.claim(session, "dead-worker", STALE).id == job_id
    assert queue.claim(session, "w2", STALE) is None
    session.execute(
        update(Job).values(heartbeat_at=utcnow() - STALE - timedelta(seconds=1))
    )
    session.commit()
    job = queue.claim(session, "w2", STALE)
    assert (job.id, job.claimed_by, job.attempts) == (job_id, "w2", 2)


def test_a_long_job_keeps_its_heartbeat_fresh(factory, settings):
    seen = []

    @handler("test.slow")
    def slow(ctx, payload):
        first = ctx.session.get(Job, ctx.job_id).heartbeat_at
        threading.Event().wait(0.5)
        with factory() as other:
            seen.append(other.get(Job, ctx.job_id).heartbeat_at > first)
        return {}

    fast = settings.model_copy(update={"worker_heartbeat_seconds": 0.1})
    try:
        with factory() as s:
            queue.enqueue(s, "test.slow")
            worker.run_one(s, factory, queue.claim(s, "w1", STALE), fast)
    finally:
        del HANDLERS["test.slow"]
    assert seen == [True]


def test_the_worker_loop_records_its_heartbeat_and_runs_jobs(factory, settings):
    quick = settings.model_copy(update={"worker_poll_seconds": 0.05})
    with factory() as s:
        job_id = queue.enqueue(s, "system.ping").id
    stop = threading.Event()
    loop = threading.Thread(target=worker.run, args=(factory, quick, stop))
    loop.start()
    try:
        for _ in range(100):
            with factory() as s:
                if s.get(Job, job_id).status == JobStatus.SUCCEEDED:
                    break
            threading.Event().wait(0.05)
    finally:
        stop.set()
        loop.join(timeout=5)
    with factory() as s:
        assert s.get(Job, job_id).status == JobStatus.SUCCEEDED
        assert s.scalars(select(WorkerHeartbeat)).one().worker_id == worker.worker_id()
