"""The placement suggestion (requirements 6.4).

1. The closest event by date on the storyteller's own timeline, inside the period whose
   dates cover the memory; a heavier event wins a tie.
2. Otherwise a new event in that period.
3. Otherwise something new: a period for the memory's decade and an event in it.

Events of the people the memory mentions, in the same window, are offered too. A memory
with no date can only be placed by hand.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.events import Event
from app.domain.memories import Memory, MemoryMention
from app.domain.participants import Participant
from app.domain.people import Person
from app.domain.periods import Period

# An event this close to the memory's dates still counts as the same moment.
NEAR = timedelta(days=31)


@dataclass
class Suggestion:
    kind: str  # "event", "period" (a new event in it), or "new"
    label: str
    reason: str
    event_id: int | None = None
    period_id: int | None = None
    person_id: int | None = None
    decade: int | None = None
    extra: dict = field(default_factory=dict)


def gap(
    a_start: date, a_end: date, b_start: date | None, b_end: date | None
) -> timedelta | None:
    """Days between two ranges (zero when they overlap); None when one is undated."""
    if b_start is None:
        return None
    b_end = b_end or b_start
    if a_start <= b_end and b_start <= a_end:
        return timedelta(0)
    return b_start - a_end if b_start > a_end else a_start - b_end


def covering_period(session: Session, person_id: int, start: date, end: date):
    """The person's narrowest period whose dates cover the memory's (open
    ends run on).
    """
    best, best_span = None, None
    for p in session.scalars(
        select(Period).where(Period.person_id == person_id, Period.deleted_at.is_(None))
    ):
        if p.start_on is None:
            continue
        p_end = p.end_on or date.max
        if p.start_on <= end and start <= p_end:
            span = (min(p_end, date(9999, 1, 1)) - p.start_on).days
            if best is None or span < best_span:
                best, best_span = p, span
    return best


def events_of(session: Session, person_id: int, period_id: int | None = None):
    stmt = (
        select(Event, Participant)
        .join(Participant, Participant.event_id == Event.id)
        .where(Participant.person_id == person_id, Event.deleted_at.is_(None))
    )
    if period_id is not None:
        stmt = stmt.where(Participant.period_id == period_id)
    return session.execute(stmt).all()


def closest(rows, start: date, end: date):
    """The nearest event within NEAR of the dates, heavier first on a tie."""
    scored = []
    for event, placement in rows:
        distance = gap(start, end, event.date_start, event.date_end)
        if distance is not None and distance <= NEAR:
            scored.append((distance, -event.weight, -event.id, event, placement))
    return min(scored, key=lambda s: s[:3])[3:] if scored else None


def decade_of(start: date) -> int:
    return start.year // 10 * 10


def suggest(
    session: Session, memory: Memory, storyteller_id: int | None
) -> list[Suggestion]:
    """Best first. Empty when the memory has no date (it waits to be placed by hand)."""
    if memory.date_start is None:
        return []
    start, end = memory.date_start, memory.date_end or memory.date_start
    out: list[Suggestion] = []
    period = (
        covering_period(session, storyteller_id, start, end) if storyteller_id else None
    )
    hit = (
        closest(events_of(session, storyteller_id, period.id), start, end)
        if period
        else None
    )
    if hit:
        event, _ = hit
        out.append(
            Suggestion(
                "event",
                f"{period.title}, {event.title}",
                "the closest event in time",
                event_id=event.id,
                period_id=period.id,
            )
        )
    if period:
        out.append(
            Suggestion(
                "period",
                f"{period.title}, a new event",
                "the period these dates fall in",
                period_id=period.id,
            )
        )
    out += others(session, memory, storyteller_id, start, end)
    decade = decade_of(start)
    out.append(
        Suggestion(
            "new",
            f"The {decade}s, a new event",
            "nothing covers these dates yet",
            decade=decade,
        )
    )
    return out


def others(session: Session, memory: Memory, storyteller_id, start: date, end: date):
    """Events of the people the memory mentions, near its dates."""
    mentioned = session.scalars(
        select(MemoryMention.person_id).where(MemoryMention.memory_id == memory.id)
    ).all()
    found = []
    for person_id in mentioned:
        if person_id == storyteller_id:
            continue
        hit = closest(events_of(session, person_id), start, end)
        if hit:
            event, _ = hit
            name = session.get(Person, person_id).name
            found.append(
                Suggestion(
                    "event",
                    f"{name}'s {event.title}",
                    f"an event in {name}'s life at that time",
                    event_id=event.id,
                    person_id=person_id,
                )
            )
    return found
