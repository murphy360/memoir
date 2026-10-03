"""Events: the moments evidence attaches to, and the knots that tie timelines together.

An event has no period of its own. Each participant places it in one of their own
periods (and optionally an epic), in `participants.py`. An event nobody has placed is in
the inbox.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    exists,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import Base, get_session
from app.domain.common import LAST_DAY, ArchiveRow, clean, live, scoped, soft_delete
from app.domain.pagination import Page, PageParams, paginate
from app.domain.places import Place
from app.domain.threads import Thread


class Event(ArchiveRow, Base):
    __tablename__ = "events"
    __table_args__ = (CheckConstraint("weight BETWEEN 1 AND 10", name="weight_1_10"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[int] = mapped_column(Integer, default=5)
    date_text: Mapped[str | None] = mapped_column(String(100))
    date_start: Mapped[date | None] = mapped_column(Date, index=True)
    date_end: Mapped[date | None] = mapped_column(Date)
    date_precision: Mapped[str | None] = mapped_column(String(16))
    location_text: Mapped[str | None] = mapped_column(String(255))
    place_id: Mapped[int | None] = mapped_column(
        ForeignKey("places.id", ondelete="SET NULL"), index=True
    )
    thread_id: Mapped[int | None] = mapped_column(
        ForeignKey("threads.id", ondelete="SET NULL"), index=True
    )
    summary: Mapped[str | None] = mapped_column(Text)
    # Reserved for the braid (requirements 5.5): "brought together", "kept apart".
    relationship_effect: Mapped[dict | None] = mapped_column(JSONB)


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    weight: int = Field(5, ge=1, le=10)
    date_text: str | None = Field(None, max_length=100)
    location_text: str | None = Field(None, max_length=255)
    place_id: int | None = None
    thread_id: int | None = None


class EventPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=180)
    description: str | None = None
    weight: int | None = Field(None, ge=1, le=10)
    date_text: str | None = Field(None, max_length=100)
    location_text: str | None = Field(None, max_length=255)
    place_id: int | None = None
    thread_id: int | None = None
    summary: str | None = None


class ParticipantOut(BaseModel):
    person_id: int
    name: str
    role: str
    source: str
    confirmed: bool
    period_id: int | None
    epic_id: int | None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    weight: int
    date_text: str | None
    date_start: date | None
    date_end: date | None
    date_precision: str | None
    location_text: str | None
    place_id: int | None
    thread_id: int | None
    summary: str | None
    participants: list[ParticipantOut] = []


def check_refs(
    session: Session, user: User, place_id: int | None, thread_id: int | None
):
    if place_id:
        live(session, Place, place_id, user, "place")
    if thread_id:
        live(session, Thread, thread_id, user, "thread")


def out(session: Session, events: list[Event]) -> list[EventOut]:
    from app.domain.participants import participants_of

    people = participants_of(session, [e.id for e in events])
    return [
        EventOut.model_validate(e).model_copy(update={"participants": people[e.id]})
        for e in events
    ]


def create(session: Session, user: User, body: EventIn) -> Event:
    check_refs(session, user, body.place_id, body.thread_id)
    event = Event(
        archive_id=user.archive_id,
        title=clean(body.title, 180),
        description=clean(body.description, 20_000),
        weight=body.weight,
        date_text=clean(body.date_text, 100),
        location_text=clean(body.location_text, 255),
        place_id=body.place_id,
        thread_id=body.thread_id,
    )
    session.add(event)
    session.commit()
    return event


TEXT_LIMITS = {
    "title": 180,
    "description": 20_000,
    "date_text": 100,
    "location_text": 255,
    "summary": 20_000,
}


def apply_patch(session: Session, user: User, event: Event, body: EventPatch) -> Event:
    sent = body.model_fields_set
    check_refs(
        session,
        user,
        body.place_id if "place_id" in sent else None,
        body.thread_id if "thread_id" in sent else None,
    )
    for field, limit in TEXT_LIMITS.items():
        if field in sent and (field != "title" or body.title):
            setattr(event, field, clean(getattr(body, field), limit))
    for field in ("place_id", "thread_id"):
        if field in sent:
            setattr(event, field, getattr(body, field))
    if "weight" in sent and body.weight:
        event.weight = body.weight
    session.commit()
    return event


def date_key():
    return [func.coalesce(Event.date_start, LAST_DAY), Event.id]


router = APIRouter(prefix="/api/events", tags=["events"])
reader = require_role(Role.VIEWER)
writer = require_role(Role.CONTRIBUTOR)


@router.get("", response_model=Page[EventOut])
def list_events(
    thread_id: int | None = Query(None),
    place_id: int | None = Query(None),
    unplaced: bool = Query(False, description="Only events no participant has placed"),
    page: PageParams = Depends(),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    from app.domain.participants import Participant

    stmt = scoped(Event, user)
    if thread_id:
        stmt = stmt.where(Event.thread_id == thread_id)
    if place_id:
        stmt = stmt.where(Event.place_id == place_id)
    if unplaced:
        placed = select(Participant.id).where(
            Participant.event_id == Event.id, Participant.period_id.is_not(None)
        )
        stmt = stmt.where(~exists(placed))
    rows, cursor = paginate(db, stmt, date_key(), page)
    return Page(items=out(db, rows), next_cursor=cursor)


@router.post("", response_model=EventOut, status_code=201)
def create_event(
    body: EventIn, user: User = Depends(writer), db: Session = Depends(get_session)
):
    return out(db, [create(db, user, body)])[0]


@router.get("/{event_id}", response_model=EventOut)
def get_event(
    event_id: int, user: User = Depends(reader), db: Session = Depends(get_session)
):
    return out(db, [live(db, Event, event_id, user, "event")])[0]


@router.patch("/{event_id}", response_model=EventOut)
def update_event(
    event_id: int,
    body: EventPatch,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    event = live(db, Event, event_id, user, "event")
    return out(db, [apply_patch(db, user, event, body)])[0]


@router.delete("/{event_id}", status_code=204)
def remove_event(
    event_id: int, user: User = Depends(writer), db: Session = Depends(get_session)
) -> None:
    """Soft delete. Its memories and photos are kept and show in the inbox."""
    soft_delete(live(db, Event, event_id, user, "event"))
    db.commit()
