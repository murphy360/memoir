"""Enqueue, claim, finish and fail jobs. Every function takes the caller's session.

Claiming uses `FOR UPDATE SKIP LOCKED`, so any number of workers can poll the same
table and each job is handed to exactly one of them. A running job whose heartbeat has
lapsed is taken to be stuck (its worker died) and is claimed again, which counts as an
attempt.
"""

from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.jobs.models import Job, JobStatus

MAX_BACKOFF = timedelta(hours=1)


def enqueue(
    session: Session,
    kind: str,
    payload: dict | None = None,
    *,
    idempotency_key: str | None = None,
    max_attempts: int = 5,
    requested_by: int | None = None,
) -> Job:
    """Add a job and commit. A key already used returns that job instead."""
    values = {
        "kind": kind,
        "payload": payload or {},
        "status": JobStatus.QUEUED,
        "attempts": 0,
        "max_attempts": max_attempts,
        "run_after": utcnow(),
        "idempotency_key": idempotency_key,
        "requested_by": requested_by,
        "progress": {},
        "created_at": utcnow(),
    }
    stmt = insert(Job).values(**values).returning(Job.id)
    if idempotency_key:
        stmt = stmt.on_conflict_do_nothing(index_elements=["idempotency_key"])
    job_id = session.execute(stmt).scalar()
    session.commit()
    if job_id is None:
        return session.scalars(
            select(Job).where(Job.idempotency_key == idempotency_key)
        ).one()
    return session.get(Job, job_id)


def claim(session: Session, worker_id: str, stale_after: timedelta) -> Job | None:
    """Take the next due job, or a stuck one, and mark it running for this worker."""
    now = utcnow()
    due = (Job.status == JobStatus.QUEUED) & (Job.run_after <= now)
    stuck = (Job.status == JobStatus.RUNNING) & (Job.heartbeat_at < now - stale_after)
    job = session.scalars(
        select(Job)
        .where(or_(due, stuck))
        .order_by(Job.run_after, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is None:
        session.rollback()
        return None
    job.status = JobStatus.RUNNING
    job.claimed_by = worker_id
    job.heartbeat_at = now
    job.attempts += 1
    session.commit()
    return job


def beat(session: Session, job_id: int, progress: dict | None = None) -> None:
    """Show the job is alive, optionally with its progress."""
    values = {"heartbeat_at": utcnow()}
    if progress is not None:
        values["progress"] = progress
    session.execute(update(Job).where(Job.id == job_id).values(**values))
    session.commit()


def succeed(session: Session, job: Job, result: dict | None) -> None:
    job.status = JobStatus.SUCCEEDED
    job.result = result or {}
    job.error = None
    job.finished_at = utcnow()
    session.commit()


def backoff(attempts: int, base_seconds: float) -> timedelta:
    return min(timedelta(seconds=base_seconds * 2 ** (attempts - 1)), MAX_BACKOFF)


def fail(
    session: Session, job: Job, error: str, *, base_seconds: float, retry: bool = True
) -> None:
    """Record the error, then queue the job again after a backoff or give up."""
    job.error = error[:2000]
    if retry and job.attempts < job.max_attempts:
        job.status = JobStatus.QUEUED
        job.run_after = utcnow() + backoff(job.attempts, base_seconds)
    else:
        job.status = JobStatus.FAILED
        job.finished_at = utcnow()
    session.commit()
