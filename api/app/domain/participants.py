"""Participants: who was at an event, and where each of them places it in their own
life.

The database enforces the placement rules: the period must be the participant's own (a
composite key on period and person) and the epic must sit in that period (a composite
key on epic and period). Both keys are checked at commit, so a merge or a move can
update both sides in one transaction.
"""

from datetime import datetime
from enum import StrEnum

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import Base, get_session, utcnow
from app.core.errors import ApiError
from app.domain.epics import Epic
from app.domain.events import Event, EventOut, ParticipantOut, date_key, out
from app.domain.pagination import Page, PageParams, paginate
from app.domain.common import live, scoped
from app.domain.people import Person
from app.domain.periods import Period


class ParticipantRole(StrEnum):
    PARTICIPANT = "participant"
    STORYTELLER = "storyteller"
    MENTIONED = "mentioned"
    IN_PHOTO = "in_photo"


class Source(StrEnum):
    CONFIRMED = "confirmed"  # a person said so
    TRANSCRIPT = "transcript"  # named in a memory, not yet confirmed
    FACE = "face"  # a confirmed face in one of the event's photos


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("event_id", "person_id", name="uq_participants_event_person"),
        CheckConstraint(
            "epic_id IS NULL OR period_id IS NOT NULL", name="epic_needs_period"
        ),
        ForeignKeyConstraint(
            ["period_id", "person_id"],
            ["periods.id", "periods.person_id"],
            name="fk_participants_own_period",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["epic_id", "period_id"],
            ["epics.id", "epics.period_id"],
            name="fk_participants_epic_in_period",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), index=True
    )
    period_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    epic_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    role: Mapped[str] = mapped_column(String(16), default=ParticipantRole.PARTICIPANT)
    source: Mapped[str] = mapped_column(String(16), default=Source.CONFIRMED)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Placement(BaseModel):
    role: ParticipantRole = ParticipantRole.PARTICIPANT
    period_id: int | None = None
    epic_id: int | None = Field(None, description="Sets the period too")


class TimelineEntry(EventOut):
    """An event as it sits in one person's life: their own period and epic for it."""

    period_id: int | None
    epic_id: int | None


def participants_of(session: Session, event_ids: list[int]) -> dict[int, list]:
    found: dict[int, list[ParticipantOut]] = {e: [] for e in event_ids}
    rows = session.execute(
        select(Participant, Person.name)
        .join(Person, Person.id == Participant.person_id)
        .where(Participant.event_id.in_(event_ids), Person.deleted_at.is_(None))
        .order_by(Participant.id)
    )
    for p, name in rows:
        found[p.event_id].append(
            ParticipantOut(
                person_id=p.person_id,
                name=name,
                role=p.role,
                source=p.source,
                confirmed=p.confirmed_at is not None,
                period_id=p.period_id,
                epic_id=p.epic_id,
            )
        )
    return found


def find(session: Session, event_id: int, person_id: int) -> Participant | None:
    return session.scalars(
        select(Participant).where(
            Participant.event_id == event_id, Participant.person_id == person_id
        )
    ).first()


def resolve_placement(
    session: Session, user: User, person: Person, body: Placement
) -> tuple[int | None, int | None]:
    """(period, epic) for a person, checked: their own period; the epic decides it."""
    if body.epic_id:
        epic = live(session, Epic, body.epic_id, user, "epic")
        period = session.get(Period, epic.period_id)
        if period.person_id != person.id:
            raise ApiError(
                422, "not_their_epic", "That epic is in someone else's life.", "epic_id"
            )
        return period.id, epic.id
    if body.period_id:
        period = live(session, Period, body.period_id, user, "period")
        if period.person_id != person.id:
            raise ApiError(
                422,
                "not_their_period",
                "That period is in someone else's life.",
                "period_id",
            )
        return period.id, None
    return None, None


def place(
    session: Session, user: User, event: Event, person: Person, body: Placement
) -> Participant:
    """Add a person to an event, or change their role or placement. A person did this,
    so the participant counts as confirmed."""
    period_id, epic_id = resolve_placement(session, user, person, body)
    row = find(session, event.id, person.id) or Participant(
        event_id=event.id, person_id=person.id
    )
    row.role, row.period_id, row.epic_id = body.role, period_id, epic_id
    row.source = row.source if row.id else Source.CONFIRMED
    row.confirmed_at, row.confirmed_by = utcnow(), user.id
    session.add(row)
    session.commit()
    return row


def ensure(
    session: Session,
    event_id: int,
    person_id: int,
    role: ParticipantRole,
    source: Source,
) -> None:
    """Make someone a participant if they are not one yet (unconfirmed).
    Caller commits.
    """
    if find(session, event_id, person_id) is None:
        session.add(
            Participant(
                event_id=event_id, person_id=person_id, role=role, source=source
            )
        )
        session.flush()


router = APIRouter(tags=["participants"])
reader = require_role(Role.VIEWER)
writer = require_role(Role.CONTRIBUTOR)


@router.put("/api/events/{event_id}/participants/{person_id}", response_model=EventOut)
def place_participant(
    event_id: int,
    person_id: int,
    body: Placement,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    event = live(db, Event, event_id, user, "event")
    place(db, user, event, live(db, Person, person_id, user, "person"), body)
    return out(db, [event])[0]


@router.post(
    "/api/events/{event_id}/participants/{person_id}/confirm", response_model=EventOut
)
def confirm_participant(
    event_id: int,
    person_id: int,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    event = live(db, Event, event_id, user, "event")
    row = find(db, event.id, person_id)
    if row is None:
        raise ApiError(404, "not_found", "That person is not at this event.")
    row.confirmed_at, row.confirmed_by = utcnow(), user.id
    db.commit()
    return out(db, [event])[0]


@router.delete(
    "/api/events/{event_id}/participants/{person_id}", response_model=EventOut
)
def remove_participant(
    event_id: int,
    person_id: int,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    event = live(db, Event, event_id, user, "event")
    row = find(db, event.id, person_id)
    if row is not None:
        db.delete(row)
        db.commit()
    return out(db, [event])[0]


@router.get("/api/people/{person_id}/events", response_model=Page[TimelineEntry])
def person_timeline(
    person_id: int,
    page: PageParams = Depends(),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    """Every event a person took part in, with the period and epic they place it in."""
    live(db, Person, person_id, user, "person")
    stmt = scoped(Event, user).join(
        Participant,
        (Participant.event_id == Event.id) & (Participant.person_id == person_id),
    )
    rows, cursor = paginate(db, stmt, date_key(), page)
    placements = {
        p.event_id: p
        for p in db.scalars(
            select(Participant).where(
                Participant.person_id == person_id,
                Participant.event_id.in_([e.id for e in rows]),
            )
        )
    }
    items = [
        TimelineEntry(
            **entry.model_dump(),
            period_id=placements[entry.id].period_id,
            epic_id=placements[entry.id].epic_id,
        )
        for entry in out(db, rows)
    ]
    return Page(items=items, next_cursor=cursor)
