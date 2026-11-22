"""What an agent can do. Each tool is a function of the database session and the
person the agent acts as, built on the same services, role checks and visibility rule
as the web app (`memories.visible_to`). server.py exposes them over MCP.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.accounts.models import RANK, Role, User
from app.archive.models import Archive
from app.capture import service as capture
from app.core.errors import ApiError
from app.core.settings import get_settings
from app.dates.store import read
from app.domain import people as people_mod
from app.domain.common import LAST_DAY, live, scoped
from app.domain.events import Event
from app.domain.memories import Memory, MemoryMention, MemoryPlace, visible, visible_to
from app.domain.pagination import PageParams, paginate
from app.domain.participants import Participant
from app.domain.people import Person, PersonAlias
from app.domain.periods import Period
from app.domain.places import Place
from app.domain.questions import Question
from app.placement.service import person_for, saved_to
from app.questions import interviewer

READ = (
    "whoami",
    "search_memories",
    "get_memory",
    "timeline",
    "list_people",
    "next_question",
)
WRITE = ("tell_story",)
MAX_PAGE = 50
SNIPPET = 160


def allowed(role: str) -> tuple[str, ...]:
    """The tools a role allows: a viewer reads, a contributor also tells stories."""
    return READ + WRITE if RANK[Role(role)] >= RANK[Role.CONTRIBUTOR] else READ


def _page(cursor: str | None, limit: int) -> PageParams:
    return PageParams(cursor=cursor, limit=max(1, min(limit, MAX_PAGE)))


def link(memory_id: int) -> str:
    return f"{get_settings().base_url}/memories/{memory_id}"


def _names(session: Session, model, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    field = model.name
    return dict(session.execute(select(model.id, field).where(model.id.in_(ids))).all())


def whoami(session: Session, user: User, client_name: str) -> dict:
    archive = session.get(Archive, user.archive_id)
    return {
        "name": user.display_name,
        "email": user.email,
        "role": user.role,
        "executor": user.is_executor,
        "archive": archive.name if archive else None,
        "person_id": interviewer.own_person_id(session, user),
        "agent": client_name,
        "tools": list(allowed(user.role)),
        "can_tell_stories": user.at_least(Role.CONTRIBUTOR),
        "app": get_settings().public_url,
    }


def _dated(stmt, date_from: str | None, date_to: str | None):
    """Memories whose dates overlap the range; an undated memory never matches."""
    start = read(date_from, "date_from", False)
    end = read(date_to, "date_to", False)
    if start:
        stmt = stmt.where(
            func.coalesce(Memory.date_end, Memory.date_start) >= start.start
        )
    if end:
        stmt = stmt.where(Memory.date_start <= end.end)
    return stmt


def _snippet(memory: Memory, words: list[str]) -> str | None:
    text = memory.transcript or memory.description or ""
    if not text:
        return None
    lower = text.lower()
    at = min((lower.find(w) for w in words if lower.find(w) >= 0), default=0)
    start = max(0, at - SNIPPET // 2)
    piece = " ".join(text[start : start + SNIPPET].split())
    return ("…" if start else "") + piece + ("…" if start + SNIPPET < len(text) else "")


def search_memories(
    session: Session,
    user: User,
    query: str | None = None,
    person_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> dict:
    stmt = visible_to(scoped(Memory, user), user)
    words = [w.lower() for w in (query or "").split()][:8]
    for word in words:
        stmt = stmt.where(
            or_(
                Memory.title.icontains(word, autoescape=True),
                Memory.description.icontains(word, autoescape=True),
                Memory.transcript.icontains(word, autoescape=True),
            )
        )
    if person_id:
        mentioned = select(MemoryMention.memory_id).where(
            MemoryMention.person_id == person_id
        )
        stmt = stmt.where(
            (Memory.storyteller_id == person_id) | Memory.id.in_(mentioned)
        )
    stmt = _dated(stmt, date_from, date_to)
    keys = [func.coalesce(Memory.date_start, LAST_DAY), Memory.id]
    rows, next_cursor = paginate(session, stmt, keys, _page(cursor, limit))
    tellers = _names(session, Person, (m.storyteller_id for m in rows))
    items = [
        {
            "id": m.id,
            "title": m.title,
            "date": m.date_text,
            "storyteller": tellers.get(m.storyteller_id),
            "told_through": m.told_through,
            "snippet": _snippet(m, words),
        }
        for m in rows
    ]
    return {"items": items, "next_cursor": next_cursor}


def _filed(session: Session, memory: Memory) -> dict | None:
    where = saved_to(session, memory)
    if where is None:
        return None
    return {
        "event_id": where.event_id,
        "event": where.event_title,
        "period_id": where.period_id,
        "period": where.period_title,
        "created_for_this_memory": where.created_for_this_memory,
    }


def get_memory(session: Session, user: User, memory_id: int) -> dict:
    m = visible(session, memory_id, user)
    mentioned = session.scalars(
        select(MemoryMention.person_id).where(MemoryMention.memory_id == m.id)
    ).all()
    placed = session.scalars(
        select(MemoryPlace.place_id).where(MemoryPlace.memory_id == m.id)
    ).all()
    question = (
        session.get(Question, m.response_to_question_id)
        if m.response_to_question_id
        else None
    )
    return {
        "id": m.id,
        "title": m.title,
        "description": m.description,
        "transcript": m.transcript,
        "date": m.date_text,
        "date_range": [str(m.date_start), str(m.date_end)] if m.date_start else None,
        "storyteller": _names(session, Person, [m.storyteller_id]).get(
            m.storyteller_id
        ),
        "people": sorted(_names(session, Person, mentioned).values()),
        "places": sorted(_names(session, Place, placed).values()),
        "filed": _filed(session, m),
        "answers_question": question.text if question else None,
        "told_through": m.told_through,
        "visibility": m.visibility,
        "recorded_at": m.recorded_at.isoformat(),
        "has_recording": m.audio_state is not None,
        "link": link(m.id),
    }


def _events(session: Session, person_id: int, period_ids: list[int] | None):
    """The person's events, in date order: in these periods, or (None) unplaced."""
    where = (
        Participant.period_id.is_(None)
        if period_ids is None
        else Participant.period_id.in_(period_ids)
    )
    rows = session.execute(
        select(Event, Participant.period_id)
        .join(Participant, Participant.event_id == Event.id)
        .where(Participant.person_id == person_id, Event.deleted_at.is_(None), where)
        .order_by(func.coalesce(Event.date_start, LAST_DAY), Event.id)
        .limit(500)
    ).all()
    return [(e, pid) for e, pid in rows]


def timeline(
    session: Session,
    user: User,
    person_id: int | None = None,
    cursor: str | None = None,
) -> dict:
    if person_id:
        person = live(session, Person, person_id, user, "person")
    else:
        person = person_for(session, user)
        session.commit()
    stmt = scoped(Period, user).where(Period.person_id == person.id)
    keys = [func.coalesce(Period.start_on, LAST_DAY), Period.id]
    periods, next_cursor = paginate(session, stmt, keys, _page(cursor, MAX_PAGE))
    events: dict[int, list[dict]] = {p.id: [] for p in periods}
    for event, period_id in _events(session, person.id, list(events)):
        events[period_id].append(
            {"id": event.id, "title": event.title, "date": event.date_text}
        )
    unplaced = (
        [
            {"id": e.id, "title": e.title, "date": e.date_text}
            for e, _ in _events(session, person.id, None)
        ]
        if cursor is None
        else []
    )
    return {
        "person": {"id": person.id, "name": person.name},
        "periods": [
            {
                "id": p.id,
                "title": p.title,
                "from": p.start_text,
                "to": p.end_text,
                "summary": p.summary,
                "events": events[p.id],
            }
            for p in periods
        ],
        "unplaced_events": unplaced,
        "next_cursor": next_cursor,
    }


def list_people(
    session: Session,
    user: User,
    query: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> dict:
    stmt = scoped(Person, user)
    if query and query.strip():
        like = query.strip()
        aliased = select(PersonAlias.person_id).where(
            PersonAlias.alias.icontains(like, autoescape=True)
        )
        stmt = stmt.where(
            Person.name.icontains(like, autoescape=True) | Person.id.in_(aliased)
        )
    keys = [func.lower(Person.name), Person.id]
    rows, next_cursor = paginate(session, stmt, keys, _page(cursor, limit))
    aliases = people_mod.aliases_of(session, [p.id for p in rows])
    items = [
        {
            "id": p.id,
            "name": p.name,
            "also_called": aliases.get(p.id, []),
            "born": p.birth_text,
            "died": p.death_text,
            "is_you": p.user_id == user.id,
            "needs_review": p.needs_review,
        }
        for p in rows
    ]
    return {"items": items, "next_cursor": next_cursor}


def next_question(session: Session, user: User) -> dict:
    interviewer.seed(session, user)
    found = interviewer.pending_for(session, user, limit=1)
    if not found:
        return {"question": None}
    q = interviewer.out(session, found[0])
    return {
        "question": {"id": q.id, "text": q.text, "about": q.about, "scope": q.scope},
        "how_to_answer": "Tell the answer with tell_story, passing this question_id.",
    }


def tell_story(
    session: Session,
    user: User,
    client_name: str,
    story: str,
    title: str | None = None,
    date: str | None = None,
    question_id: int | None = None,
) -> dict:
    if not user.at_least(Role.CONTRIBUTOR):
        raise ApiError(403, "forbidden", "Your role does not allow this.")
    memory = capture.tell(
        session,
        user,
        story,
        title=title,
        date_text=date,
        question_id=question_id,
        told_through=client_name,
    )
    filed = _filed(session, memory)
    if filed:
        status = "filed"
    elif memory.autofiled_at:
        status = "waiting to be placed: it is in the inbox"
    else:
        status = "saved: Memoir files it once it has read the story"
    return {
        "memory_id": memory.id,
        "title": memory.title,
        "date": memory.date_text,
        "status": status,
        "filed": filed,
        "link": link(memory.id),
    }
