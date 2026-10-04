"""Placing a memory: on an event, in a period as a new event, or somewhere new; and
auto-filing a quick memory where the suggestion says, once.

Auto-created periods and events record the memory they were made for and are labelled
"created for this memory". They are ordinary rows afterwards: no job ever makes them
again, and a memory is auto-filed at most once, so deleting what was made sticks.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.core.db import utcnow
from app.core.errors import ApiError
from app.dates.store import set_point, set_range
from app.domain.events import Event
from app.domain.memories import Memory, join_event
from app.domain.participants import Participant, ParticipantRole, Source
from app.domain.people import Person
from app.domain.periods import Period, _slug
from app.domain.settings import settings_for
from app.placement.suggest import Suggestion, suggest


def person_for(session: Session, user: User) -> Person:
    """The user's own person in the archive, made from their name the first time."""
    person = session.scalars(
        select(Person).where(Person.user_id == user.id, Person.deleted_at.is_(None))
    ).first()
    if person is None:
        taken = session.scalars(
            select(Person).where(
                Person.archive_id == user.archive_id,
                Person.name == user.display_name,
                Person.deleted_at.is_(None),
                Person.user_id.is_(None),
            )
        ).first()
        person = taken or Person(archive_id=user.archive_id, name=user.display_name)
        person.user_id = user.id
        session.add(person)
        session.flush()
    return person


def storyteller_of(session: Session, memory: Memory) -> int | None:
    if memory.storyteller_id:
        return memory.storyteller_id
    user = session.get(User, memory.uploaded_by) if memory.uploaded_by else None
    return person_for(session, user).id if user else None


def _placement(session: Session, event_id: int, person_id: int, period_id, auto: bool):
    row = session.scalars(
        select(Participant).where(
            Participant.event_id == event_id, Participant.person_id == person_id
        )
    ).first() or Participant(
        event_id=event_id, person_id=person_id, role=ParticipantRole.STORYTELLER
    )
    if period_id and row.period_id is None:
        row.period_id = period_id
    row.source = row.source or (Source.TRANSCRIPT if auto else Source.CONFIRMED)
    if not auto and row.confirmed_at is None:
        row.confirmed_at = utcnow()
    session.add(row)
    session.flush()


def on_event(
    session: Session, memory: Memory, event: Event, person_id, period_id, auto=False
):
    memory.event_id = event.id
    if person_id:
        _placement(session, event.id, person_id, period_id, auto)
    join_event(session, memory)


def new_event(
    session: Session,
    memory: Memory,
    period: Period | None,
    person_id,
    auto: bool,
    title: str | None = None,
    date_text: str | None = None,
) -> Event:
    event = Event(
        archive_id=memory.archive_id,
        title=(title or memory.title or "A memory")[:180],
        weight=5,
        auto_created_for_memory_id=memory.id if auto else None,
    )
    text = date_text if date_text is not None else memory.date_text
    set_point(event, "date", text, "memory" if auto else "manual", keep=True)
    session.add(event)
    session.flush()
    on_event(session, memory, event, person_id, period.id if period else None, auto)
    return event


def decade_period(
    session: Session, memory: Memory, person_id: int, decade: int, auto: bool
):
    period = Period(
        archive_id=memory.archive_id,
        person_id=person_id,
        title=f"The {decade}s",
        slug=_slug(session, person_id, f"The {decade}s"),
        auto_created_for_memory_id=memory.id if auto else None,
    )
    set_range(period, str(decade), str(decade + 9), "memory" if auto else "manual")
    session.add(period)
    session.flush()
    return period


def apply(
    session: Session, memory: Memory, choice: Suggestion, person_id, auto: bool
) -> None:
    if choice.kind == "event":
        event = session.get(Event, choice.event_id)
        on_event(session, memory, event, person_id, choice.period_id, auto)
    elif choice.kind == "period":
        new_event(
            session, memory, session.get(Period, choice.period_id), person_id, auto
        )
    else:
        period = decade_period(session, memory, person_id, choice.decade, auto)
        new_event(session, memory, period, person_id, auto)


def autofile(session: Session, memory: Memory) -> bool:
    """File a quick memory, or an answer to a question, where the suggestion says. Once
    only, and never undone by a job.
    """
    context = memory.capture_context or {}
    hands_free = context.get("quick") or memory.response_to_question_id
    if memory.event_id or memory.autofiled_at or not hands_free:
        return False
    if not settings_for(session, memory.archive_id).auto_file_quick_memories:
        return False
    memory.autofiled_at = utcnow()
    person_id = storyteller_of(session, memory)
    choices = suggest(session, memory, person_id)
    if not choices or person_id is None:
        session.commit()
        return False
    apply(session, memory, choices[0], person_id, auto=True)
    session.commit()
    return True


@dataclass
class SavedTo:
    event_id: int
    event_title: str
    period_id: int | None
    period_title: str | None
    created_for_this_memory: bool


def saved_to(session: Session, memory: Memory) -> SavedTo | None:
    """Where the memory is, as the storyteller sees it: their period, then the event."""
    event = session.get(Event, memory.event_id) if memory.event_id else None
    if event is None or event.deleted_at is not None:
        return None
    person_id = storyteller_of(session, memory)
    placement = session.scalars(
        select(Participant).where(
            Participant.event_id == event.id, Participant.person_id == person_id
        )
    ).first()
    period = (
        session.get(Period, placement.period_id)
        if placement and placement.period_id
        else None
    )
    if period is not None and period.deleted_at is not None:
        period = None
    return SavedTo(
        event_id=event.id,
        event_title=event.title,
        period_id=period.id if period else None,
        period_title=period.title if period else None,
        created_for_this_memory=event.auto_created_for_memory_id == memory.id,
    )


def check_event(session: Session, user: User, event_id: int) -> Event:
    event = session.get(Event, event_id)
    if event is None or event.archive_id != user.archive_id or event.deleted_at:
        raise ApiError(404, "not_found", "No such event.", "event_id")
    return event
