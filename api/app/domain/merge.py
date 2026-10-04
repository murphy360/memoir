"""Merging two of the same thing into one (requirements 3.2). The source is
soft-deleted.

Events: memories, photos, participants and questions move; the target's empty fields are
filled from the source. People: periods, placements, memories, mentions, aliases and the
login move, and the source's name stays on as an alias. Periods (same person only):
epics and placements move.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import get_session
from app.core.errors import ApiError
from app.domain import events as events_mod
from app.domain import people as people_mod
from app.domain.assets import EventAsset
from app.domain.common import live, soft_delete
from app.domain.events import Event, EventOut
from app.domain.memories import Memory, MemoryMention
from app.domain.participants import Participant
from app.domain.people import Person, PersonAlias, PersonOut
from app.domain.periods import Period, PeriodOut, _slug, move_contents
from app.domain.questions import Question

EVENT_FIELDS = (
    "description",
    "date_text",
    "date_start",
    "date_end",
    "date_precision",
    "date_source",
    "location_text",
    "place_id",
    "thread_id",
    "summary",
)
PERSON_FIELDS = (
    "phone",
    "email",
    "address",
    "notes",
    "birth_text",
    "birth_start",
    "birth_end",
    "birth_source",
    "death_text",
    "death_start",
    "death_end",
    "death_source",
)


class MergeInto(BaseModel):
    into_id: int


def _fill(target, source, fields) -> None:
    for field in fields:
        if getattr(target, field) in (None, "") and getattr(source, field) not in (
            None,
            "",
        ):
            setattr(target, field, getattr(source, field))


def _different(source_id: int, target_id: int, what: str) -> None:
    if source_id == target_id:
        raise ApiError(
            422, "same_thing", f"Choose another {what} to merge into.", "into_id"
        )


def merge_events(session: Session, source: Event, target: Event) -> Event:
    _different(source.id, target.id, "event")
    session.execute(
        update(Memory).where(Memory.event_id == source.id).values(event_id=target.id)
    )
    session.execute(
        update(Question)
        .where(Question.event_id == source.id)
        .values(event_id=target.id)
    )
    have = set(
        session.scalars(
            select(EventAsset.asset_id).where(EventAsset.event_id == target.id)
        )
    )
    for link in session.scalars(
        select(EventAsset).where(EventAsset.event_id == source.id)
    ):
        if link.asset_id in have:
            session.delete(link)
        else:
            link.event_id = target.id
    _move_participants(session, source.id, target.id)
    _fill(target, source, EVENT_FIELDS)
    soft_delete(source)
    session.commit()
    return target


def _move_participants(session: Session, source_id: int, target_id: int) -> None:
    there = {
        p.person_id: p
        for p in session.scalars(
            select(Participant).where(Participant.event_id == target_id)
        )
    }
    for row in session.scalars(
        select(Participant).where(Participant.event_id == source_id)
    ):
        kept = there.get(row.person_id)
        if kept is None:
            row.event_id = target_id
            continue
        if kept.period_id is None and row.period_id is not None:
            kept.period_id, kept.epic_id = row.period_id, row.epic_id
        kept.confirmed_at = kept.confirmed_at or row.confirmed_at
        session.delete(row)
    session.flush()


def merge_people(
    session: Session, user: User, source: Person, target: Person
) -> Person:
    _different(source.id, target.id, "person")
    if source.user_id and target.user_id:
        raise ApiError(
            409, "two_logins", "Both people have their own login; keep them separate."
        )
    _merge_participants(session, source.id, target.id)
    moving = session.scalars(
        select(Period).where(Period.person_id == source.id, Period.deleted_at.is_(None))
    ).all()
    for period in moving:
        # The free slug among the target's periods first, then both changes at once.
        slug = _slug(session, target.id, period.title, period.id)
        with session.no_autoflush:
            period.person_id, period.slug = target.id, slug
        session.flush()
    session.execute(
        update(Participant)
        .where(Participant.person_id == source.id)
        .values(person_id=target.id)
    )
    session.execute(
        update(Memory)
        .where(Memory.storyteller_id == source.id)
        .values(storyteller_id=target.id)
    )
    _merge_mentions(session, source.id, target.id)
    session.execute(
        update(Question)
        .where(Question.person_id == source.id)
        .values(person_id=target.id)
    )
    _merge_aliases(session, source, target)
    _fill(target, source, PERSON_FIELDS)
    if source.user_id and not target.user_id:
        target.user_id, source.user_id = source.user_id, None
        session.flush()
    soft_delete(source)
    session.commit()
    return target


def _merge_participants(session: Session, source_id: int, target_id: int) -> None:
    """Where both took part in an event, keep one participant: the target, placed in the
    source's period if the target had none (the period moves to the target too)."""
    mine = {
        p.event_id: p
        for p in session.scalars(
            select(Participant).where(Participant.person_id == target_id)
        )
    }
    for row in session.scalars(
        select(Participant).where(Participant.person_id == source_id)
    ):
        kept = mine.get(row.event_id)
        if kept is None:
            continue
        if kept.period_id is None and row.period_id is not None:
            # The period becomes the target's in the same transaction (checked at
            # commit).
            kept.period_id, kept.epic_id = row.period_id, row.epic_id
        session.delete(row)
    session.flush()


def _merge_mentions(session: Session, source_id: int, target_id: int) -> None:
    both = select(MemoryMention.memory_id).where(MemoryMention.person_id == target_id)
    session.execute(
        delete(MemoryMention).where(
            MemoryMention.person_id == source_id, MemoryMention.memory_id.in_(both)
        )
    )
    session.execute(
        update(MemoryMention)
        .where(MemoryMention.person_id == source_id)
        .values(person_id=target_id)
    )


def _merge_aliases(session: Session, source: Person, target: Person) -> None:
    """The source's name and aliases become the target's aliases (once each)."""
    have = {
        a.alias.lower()
        for a in session.scalars(
            select(PersonAlias).where(PersonAlias.person_id == target.id)
        )
    }
    have.add(target.name.lower())
    names = [source.name] + [
        a.alias
        for a in session.scalars(
            select(PersonAlias).where(PersonAlias.person_id == source.id)
        )
    ]
    session.execute(delete(PersonAlias).where(PersonAlias.person_id == source.id))
    for name in names:
        if name.lower() not in have:
            session.add(PersonAlias(person_id=target.id, alias=name))
            have.add(name.lower())
    session.flush()


def merge_periods(session: Session, source: Period, target: Period) -> Period:
    _different(source.id, target.id, "period")
    if source.person_id != target.person_id:
        raise ApiError(
            422, "bad_target", "Periods merge only within one person's life.", "into_id"
        )
    move_contents(session, source, target)
    dates = ("start_text", "start_on", "end_text", "end_on", "dates_source")
    _fill(target, source, (*dates, "summary"))
    soft_delete(source)
    session.commit()
    return target


router = APIRouter(tags=["merge"])
writer = require_role(Role.CONTRIBUTOR)


@router.post("/api/events/{event_id}/merge", response_model=EventOut)
def merge_event(
    event_id: int,
    body: MergeInto,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    source = live(db, Event, event_id, user, "event")
    target = live(db, Event, body.into_id, user, "event")
    return events_mod.out(db, [merge_events(db, source, target)])[0]


@router.post("/api/people/{person_id}/merge", response_model=PersonOut)
def merge_person(
    person_id: int,
    body: MergeInto,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    source = live(db, Person, person_id, user, "person")
    target = live(db, Person, body.into_id, user, "person")
    return people_mod.out(db, [merge_people(db, user, source, target)])[0]


@router.post("/api/periods/{period_id}/merge", response_model=PeriodOut)
def merge_period(
    period_id: int,
    body: MergeInto,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    source = live(db, Period, period_id, user, "period")
    target = live(db, Period, body.into_id, user, "period")
    return merge_periods(db, source, target)
