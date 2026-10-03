"""GET /api/health: is the database reachable, and is a worker alive?"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.core.db import get_session, utcnow
from app.core.errors import ApiError, ErrorResponse
from app.core.settings import Settings, get_settings
from app.jobs.models import WorkerHeartbeat

router = APIRouter(tags=["health"])


class WorkerHealth(BaseModel):
    status: Literal["ok", "stale", "never"]
    last_seen: datetime | None = None
    age_seconds: float | None = None


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["ok"]
    worker: WorkerHealth


def worker_health(session: Session, settings: Settings) -> WorkerHealth:
    last = session.scalar(select(func.max(WorkerHeartbeat.last_seen)))
    if last is None:
        return WorkerHealth(status="never")
    age = (utcnow() - last).total_seconds()
    status = "ok" if age <= settings.worker_alive_seconds else "stale"
    return WorkerHealth(status=status, last_seen=last, age_seconds=round(age, 1))


@router.get(
    "/api/health",
    response_model=Health,
    responses={503: {"model": ErrorResponse, "description": "The database is down"}},
)
def health(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Health:
    try:
        session.execute(text("SELECT 1"))
        worker = worker_health(session, settings)
    except SQLAlchemyError as exc:
        raise ApiError(
            503, "database_unavailable", "The database is not reachable."
        ) from exc
    overall = "ok" if worker.status == "ok" else "degraded"
    return Health(status=overall, version=__version__, database="ok", worker=worker)
