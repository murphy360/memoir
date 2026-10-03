"""Placement, the inbox ("Waiting to be placed") and a person's timeline."""

from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import get_session
from app.core.errors import ApiError
from app.domain import memories, people
from app.domain.common import LAST_DAY, live, scoped
from app.domain.epics import Epic
from app.domain.events import Event
from app.domain.pagination import Page, PageParams, paginate
from app.domain.participants import Participant
from app.domain.people import Person
from app.dates.store import set_range
from app.domain.periods import Period, PeriodOut, _slug
from app.placement import service
from app.placement.suggest import Suggestion, suggest

router = APIRouter(tags=["placement"])
reader = require_role(Role.VIEWER)
writer = require_role(Role.CONTRIBUTOR)


class SuggestionOut(BaseModel):
    kind: str
    label: str
    reason: str
    event_id: int | None = None
    period_id: int | None = None
    person_id: int | None = None
    decade: int | None = None


class SavedToOut(BaseModel):
    event_id: int
    event_title: str
    period_id: int | None
    period_title: str | None
    created_for_this_memory: bool


class EventChoice(BaseModel):
    id: int
    title: str
    date_text: str | None


class MemoryPlacement(BaseModel):
    saved_to: SavedToOut | None
    suggestions: list[SuggestionOut]
    recent: list[EventChoice]
    nearby: list[EventChoice]


class NewPeriod(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    start_text: str | None = Field(None, max_length=100)
    end_text: str | None = Field(None, max_length=100)


class PlaceMemory(BaseModel):
    """One of: an event; a period (a new event in it); or something new."""

    event_id: int | None = None
    period_id: int | None = None
    new_period: NewPeriod | None = None
    title: str | None = Field(None, max_length=180, description="For a new event")
    date_text: str | None = Field(None, max_length=100, description="For a new event")


def _same_named(session: Session, person_id: int, title: str) -> Period | None:
    """A period of that name already in the person's life: reuse it, never a twin."""
    return session.scalars(
        select(Period).where(
            Period.person_id == person_id,
            func.lower(Period.title) == title.strip().lower(),
            Period.deleted_at.is_(None),
        )
    ).first()


def _new_period(
    session: Session, user: User, person_id: int, body: NewPeriod
) -> Period:
    period = Period(
        archive_id=user.archive_id,
        person_id=person_id,
        title=body.title.strip(),
        slug=_slug(session, person_id, body.title),
    )
    set_range(period, body.start_text, body.end_text, "manual")
    session.add(period)
    session.flush()
    return period


class Placed(BaseModel):
    memory: memories.MemoryOut
    saved_to: SavedToOut | None


def _saved(session: Session, memory) -> SavedToOut | None:
    where = service.saved_to(session, memory)
    return SavedToOut(**where.__dict__) if where else None


def _out(s: Suggestion) -> SuggestionOut:
    return SuggestionOut(**{k: v for k, v in s.__dict__.items() if k != "extra"})


def _pick(rows) -> list[EventChoice]:
    return [EventChoice(id=e.id, title=e.title, date_text=e.date_text) for e in rows]


def _choices(session: Session, person_id: int | None, memory, user: User):
    if person_id is None:
        return [], []
    mine = (
        select(Event)
        .join(Participant, Participant.event_id == Event.id)
        .where(Participant.person_id == person_id, Event.deleted_at.is_(None))
    )
    recent = session.scalars(mine.order_by(Event.created_at.desc()).limit(5)).all()
    nearby = []
    if memory.date_start:
        lo, hi = (
            memory.date_start - timedelta(days=5 * 365),
            memory.date_start + timedelta(days=5 * 365),
        )
        nearby = session.scalars(
            mine.where(Event.date_start.between(lo, hi))
            .order_by(func.abs(Event.date_start - memory.date_start))
            .limit(10)
        ).all()
    return _pick(recent), _pick(nearby)


@router.get("/api/memories/{memory_id}/placement", response_model=MemoryPlacement)
def placement(
    memory_id: int, user: User = Depends(reader), db: Session = Depends(get_session)
):
    memory = memories.visible(db, memory_id, user)
    person_id = service.storyteller_of(db, memory)
    db.commit()
    recent, nearby = _choices(db, person_id, memory, user)
    return MemoryPlacement(
        saved_to=_saved(db, memory),
        suggestions=[_out(s) for s in suggest(db, memory, person_id)],
        recent=recent,
        nearby=nearby,
    )


@router.post("/api/memories/{memory_id}/place", response_model=Placed)
def place(
    memory_id: int,
    body: PlaceMemory,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    memory = memories.visible(db, memory_id, user)
    person_id = service.storyteller_of(db, memory)
    if body.event_id:
        event = service.check_event(db, user, body.event_id)
        service.on_event(db, memory, event, person_id, None)
    elif body.period_id:
        period = live(db, Period, body.period_id, user, "period")
        service.new_event(
            db, memory, period, person_id, False, body.title, body.date_text
        )
    elif body.new_period:
        period = _same_named(db, person_id, body.new_period.title) or _new_period(
            db, user, person_id, body.new_period
        )
        service.new_event(
            db, memory, period, person_id, False, body.title, body.date_text
        )
    else:
        raise ApiError(422, "nowhere", "Choose an event, a period or something new.")
    db.commit()
    return Placed(memory=memories.out(db, [memory])[0], saved_to=_saved(db, memory))


class InboxItem(BaseModel):
    memory: memories.MemoryOut
    suggestion: SuggestionOut | None


@router.get("/api/inbox", response_model=Page[InboxItem])
def inbox(
    page: PageParams = Depends(),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    """Memories waiting to be placed, each with where Memoir would put it."""
    stmt = memories.inbox_filter(
        memories.visible_to(scoped(memories.Memory, user), user)
    )
    keys = [memories.Memory.created_at, memories.Memory.id]
    rows, cursor = paginate(db, stmt, keys, page)
    items = []
    for memory, out in zip(rows, memories.out(db, rows)):
        options = suggest(db, memory, service.storyteller_of(db, memory))
        items.append(
            InboxItem(memory=out, suggestion=_out(options[0]) if options else None)
        )
    db.commit()
    return Page(items=items, next_cursor=cursor)


@router.post("/api/inbox/{memory_id}/accept", response_model=Placed)
def accept(
    memory_id: int, user: User = Depends(writer), db: Session = Depends(get_session)
):
    """One tap: place the memory where the suggestion says."""
    memory = memories.visible(db, memory_id, user)
    person_id = service.storyteller_of(db, memory)
    options = suggest(db, memory, person_id)
    if not options:
        raise ApiError(
            409, "no_suggestion", "This memory has no date yet: choose where it goes."
        )
    service.apply(db, memory, options[0], person_id, auto=False)
    db.commit()
    return Placed(memory=memories.out(db, [memory])[0], saved_to=_saved(db, memory))


class TimelinePeriod(PeriodOut):
    event_count: int
    epic_count: int
    created_for_memory: bool


class Timeline(BaseModel):
    person: people.PersonOut
    periods: list[TimelinePeriod]
    next_cursor: str | None
    unplaced_events: int


def _counts(session: Session, person_id: int, period_ids: list[int]):
    events = dict(
        session.execute(
            select(Participant.period_id, func.count())
            .join(Event, Event.id == Participant.event_id)
            .where(
                Participant.person_id == person_id,
                Participant.period_id.in_(period_ids),
                Event.deleted_at.is_(None),
            )
            .group_by(Participant.period_id)
        ).all()
    )
    epics = dict(
        session.execute(
            select(Epic.period_id, func.count())
            .where(Epic.period_id.in_(period_ids), Epic.deleted_at.is_(None))
            .group_by(Epic.period_id)
        ).all()
    )
    return events, epics


@router.get("/api/people/{person_id}/timeline", response_model=Timeline)
def timeline(
    person_id: int,
    page: PageParams = Depends(),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    """A person's chapters in order, with how much each holds. Events load
    per period.
    """
    person = live(db, Person, person_id, user, "person")
    stmt = scoped(Period, user).where(Period.person_id == person.id)
    rows, cursor = paginate(
        db, stmt, [func.coalesce(Period.start_on, LAST_DAY), Period.id], page
    )
    events, epics = _counts(db, person.id, [p.id for p in rows])
    unplaced = db.scalar(
        select(func.count())
        .select_from(Participant)
        .join(Event, Event.id == Participant.event_id)
        .where(
            Participant.person_id == person.id,
            Participant.period_id.is_(None),
            Event.deleted_at.is_(None),
        )
    )
    return Timeline(
        person=people.out(db, [person])[0],
        periods=[
            TimelinePeriod(
                **PeriodOut.model_validate(p).model_dump(),
                event_count=events.get(p.id, 0),
                epic_count=epics.get(p.id, 0),
                created_for_memory=p.auto_created_for_memory_id is not None,
            )
            for p in rows
        ],
        next_cursor=cursor,
        unplaced_events=unplaced,
    )


@router.get("/api/me/person", response_model=people.PersonOut)
def my_person(user: User = Depends(reader), db: Session = Depends(get_session)):
    """The signed-in user's own person: their timeline starts here."""
    person = service.person_for(db, user)
    db.commit()
    return people.out(db, [person])[0]
