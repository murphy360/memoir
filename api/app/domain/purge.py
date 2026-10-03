"""Purging: soft-deleted rows are kept 30 days (the trash), then removed for good.

The owner may purge now, and a nightly job purges what is older than 30 days. Rows go in
an order the foreign keys allow; links to them follow their delete rules (cascade or set
null). Placements are taken off an epic or a period explicitly before it goes, because
the placement keys are checked, not acted on. A blob's file is left alone here: it may
be shared, and blob cleanup is its own job.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import get_session, utcnow
from app.domain.assets import Asset
from app.domain.epics import Epic
from app.domain.events import Event
from app.domain.memories import Memory
from app.domain.participants import Participant
from app.domain.people import Person
from app.domain.periods import Period
from app.domain.places import Place
from app.domain.questions import Question
from app.domain.threads import Thread
from app.jobs.registry import JobContext, handler

KEEP_DAYS = 30
# Children before parents, so each delete sees its foreign keys' rules, never a refusal.
ORDER = (Question, Memory, Asset, Epic, Event, Period, Person, Place, Thread)


class Purged(BaseModel):
    counts: dict[str, int]


def _gone(model, archive_id: int | None, cutoff):
    cond = model.deleted_at.is_not(None) & (model.deleted_at <= cutoff)
    return cond & (model.archive_id == archive_id) if archive_id is not None else cond


def _unplace(session: Session, archive_id: int | None, cutoff) -> None:
    """Take placements off the epics and periods about to go."""
    epics = select(Epic.id).where(_gone(Epic, archive_id, cutoff))
    periods = select(Period.id).where(_gone(Period, archive_id, cutoff))
    session.execute(
        update(Participant).where(Participant.epic_id.in_(epics)).values(epic_id=None)
    )
    session.execute(
        update(Participant)
        .where(Participant.period_id.in_(periods))
        .values(period_id=None, epic_id=None)
    )
    in_gone_periods = select(Epic.id).where(Epic.period_id.in_(periods))
    session.execute(
        update(Participant)
        .where(Participant.epic_id.in_(in_gone_periods))
        .values(epic_id=None)
    )


def purge(session: Session, archive_id: int | None, older_than: timedelta) -> dict:
    cutoff = utcnow() - older_than
    _unplace(session, archive_id, cutoff)
    counts = {}
    for model in ORDER:
        stmt = delete(model).where(_gone(model, archive_id, cutoff))
        counts[model.__tablename__] = session.execute(stmt).rowcount
    session.commit()
    return counts


@handler("domain.purge")
def purge_job(ctx: JobContext, payload: dict) -> dict:
    """The nightly purge, across every archive."""
    return purge(ctx.session, None, timedelta(days=payload.get("days", KEEP_DAYS)))


router = APIRouter(prefix="/api/trash", tags=["trash"])


@router.post("/purge", response_model=Purged)
def purge_now(
    older_than_days: int = Query(KEEP_DAYS, ge=0, le=3650),
    user: User = Depends(require_role(Role.OWNER)),
    db: Session = Depends(get_session),
):
    """Remove for good what was deleted more than `older_than_days` ago (0:
    everything).
    """
    return Purged(counts=purge(db, user.archive_id, timedelta(days=older_than_days)))
