"""Memories: told stories. Each belongs to one event once placed; until then, the inbox.

Visibility: a memory marked "only_me" is seen only by the account that uploaded it and
by the storyteller's own account. Every query that returns memories applies
`visible_to`.
"""

from datetime import date, datetime
from enum import StrEnum

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    delete,
    func,
    or_,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import Base, get_session, utcnow
from app.core.errors import ApiError
from app.dates.store import MANUAL, set_point
from app.domain.common import LAST_DAY, ArchiveRow, clean, live, scoped, soft_delete
from app.domain.events import Event
from app.domain.pagination import Page, PageParams, paginate
from app.domain.participants import ParticipantRole, Source, ensure
from app.domain.people import Person
from app.domain.places import Place


class Visibility(StrEnum):
    ARCHIVE = "archive"
    ONLY_ME = "only_me"


class Memory(ArchiveRow, Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), index=True
    )
    storyteller_id: Mapped[int | None] = mapped_column(
        ForeignKey("people.id", ondelete="SET NULL"), index=True
    )
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str | None] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    date_text: Mapped[str | None] = mapped_column(String(100))
    date_start: Mapped[date | None] = mapped_column(Date)
    date_end: Mapped[date | None] = mapped_column(Date)
    date_precision: Mapped[str | None] = mapped_column(String(16))
    date_source: Mapped[str | None] = mapped_column(String(16))
    tone: Mapped[str | None] = mapped_column(String(16))
    visibility: Mapped[str] = mapped_column(String(16), default=Visibility.ARCHIVE)
    response_to_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL", use_alter=True)
    )


class MemoryMention(Base):
    __tablename__ = "memory_mentions"
    __table_args__ = (UniqueConstraint("memory_id", "person_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    memory_id: Mapped[int] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"), index=True
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), index=True
    )


class MemoryPlace(Base):
    __tablename__ = "memory_places"
    __table_args__ = (UniqueConstraint("memory_id", "place_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    memory_id: Mapped[int] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"), index=True
    )
    place_id: Mapped[int] = mapped_column(
        ForeignKey("places.id", ondelete="CASCADE"), index=True
    )


class MemoryIn(BaseModel):
    title: str | None = Field(None, max_length=180)
    description: str | None = None
    transcript: str | None = None
    date_text: str | None = Field(None, max_length=100)
    storyteller_id: int | None = None
    event_id: int | None = None
    visibility: Visibility = Visibility.ARCHIVE
    mentioned_ids: list[int] = []
    place_ids: list[int] = []
    keep_text_only: bool = Field(
        False, description="Save a date Memoir cannot read, as text only"
    )


class MemoryPatch(BaseModel):
    title: str | None = Field(None, max_length=180)
    description: str | None = None
    transcript: str | None = None
    date_text: str | None = Field(None, max_length=100)
    storyteller_id: int | None = None
    event_id: int | None = None
    visibility: Visibility | None = None
    mentioned_ids: list[int] | None = None
    place_ids: list[int] | None = None
    keep_text_only: bool = Field(
        False, description="Save a date Memoir cannot read, as text only"
    )


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int | None
    storyteller_id: int | None
    uploaded_by: int | None
    title: str | None
    description: str | None
    transcript: str | None
    recorded_at: datetime
    date_text: str | None
    date_start: date | None
    date_end: date | None
    date_precision: str | None
    tone: str | None
    visibility: Visibility
    mentioned_ids: list[int] = []
    place_ids: list[int] = []


def visible_to(stmt, user: User):
    """Only memories this user may see (every memory query goes through this)."""
    own_people = select(Person.id).where(Person.user_id == user.id)
    return stmt.where(
        or_(
            Memory.visibility == Visibility.ARCHIVE,
            Memory.uploaded_by == user.id,
            Memory.storyteller_id.in_(own_people),
        )
    )


def visible(session: Session, memory_id: int, user: User) -> Memory:
    memory = live(session, Memory, memory_id, user, "memory")
    seen = visible_to(select(Memory.id), user).where(Memory.id == memory.id)
    if session.scalars(seen).first() is None:
        raise ApiError(404, "not_found", "No such memory.")
    return memory


def out(session: Session, memories: list[Memory]) -> list[MemoryOut]:
    ids = [m.id for m in memories]
    mentions: dict[int, list[int]] = {i: [] for i in ids}
    places: dict[int, list[int]] = {i: [] for i in ids}
    for m in session.scalars(
        select(MemoryMention).where(MemoryMention.memory_id.in_(ids))
    ):
        mentions[m.memory_id].append(m.person_id)
    for p in session.scalars(select(MemoryPlace).where(MemoryPlace.memory_id.in_(ids))):
        places[p.memory_id].append(p.place_id)
    return [
        MemoryOut.model_validate(m).model_copy(
            update={"mentioned_ids": mentions[m.id], "place_ids": places[m.id]}
        )
        for m in memories
    ]


def _set_links(session: Session, user: User, memory: Memory, people, places) -> None:
    if people is not None:
        for pid in people:
            live(session, Person, pid, user, "person")
        session.execute(
            delete(MemoryMention).where(MemoryMention.memory_id == memory.id)
        )
        session.add_all(
            MemoryMention(memory_id=memory.id, person_id=p) for p in set(people)
        )
    if places is not None:
        for pid in places:
            live(session, Place, pid, user, "place")
        session.execute(delete(MemoryPlace).where(MemoryPlace.memory_id == memory.id))
        session.add_all(
            MemoryPlace(memory_id=memory.id, place_id=p) for p in set(places)
        )
    session.flush()


def join_event(session: Session, memory: Memory) -> None:
    """The storyteller and everyone mentioned become participants of the memory's event,
    unconfirmed until a person confirms (requirements 3.2)."""
    if memory.event_id is None:
        return
    if memory.storyteller_id:
        ensure(
            session,
            memory.event_id,
            memory.storyteller_id,
            ParticipantRole.STORYTELLER,
            Source.TRANSCRIPT,
        )
    for mention in session.scalars(
        select(MemoryMention).where(MemoryMention.memory_id == memory.id)
    ):
        ensure(
            session,
            memory.event_id,
            mention.person_id,
            ParticipantRole.MENTIONED,
            Source.TRANSCRIPT,
        )


def create(session: Session, user: User, body: MemoryIn) -> Memory:
    if body.storyteller_id:
        live(session, Person, body.storyteller_id, user, "person")
    if body.event_id:
        live(session, Event, body.event_id, user, "event")
    memory = Memory(
        archive_id=user.archive_id,
        event_id=body.event_id,
        storyteller_id=body.storyteller_id,
        uploaded_by=user.id,
        title=clean(body.title, 180),
        description=clean(body.description, 20_000),
        transcript=body.transcript,
        visibility=body.visibility,
    )
    set_point(memory, "date", body.date_text, MANUAL, body.keep_text_only)
    session.add(memory)
    session.flush()
    _set_links(session, user, memory, body.mentioned_ids, body.place_ids)
    join_event(session, memory)
    session.commit()
    return memory


def apply_patch(
    session: Session, user: User, memory: Memory, body: MemoryPatch
) -> Memory:
    sent = body.model_fields_set
    if "storyteller_id" in sent:
        if body.storyteller_id:
            live(session, Person, body.storyteller_id, user, "person")
        memory.storyteller_id = body.storyteller_id
    if "event_id" in sent:
        if body.event_id:
            live(session, Event, body.event_id, user, "event")
        memory.event_id = body.event_id
    for field, limit in (("title", 180), ("description", 20_000)):
        if field in sent:
            setattr(memory, field, clean(getattr(body, field), limit))
    if "date_text" in sent:
        set_point(memory, "date", body.date_text, MANUAL, body.keep_text_only)
    if "transcript" in sent:
        memory.transcript = body.transcript
    if "visibility" in sent and body.visibility:
        memory.visibility = body.visibility
    _set_links(session, user, memory, body.mentioned_ids, body.place_ids)
    join_event(session, memory)
    session.commit()
    return memory


def inbox_filter(stmt):
    """Memories with no live event: never placed, or their event was deleted."""
    live_event = select(Event.id).where(
        Event.id == Memory.event_id, Event.deleted_at.is_(None)
    )
    return stmt.where(~live_event.exists())


router = APIRouter(prefix="/api/memories", tags=["memories"])
reader = require_role(Role.VIEWER)
writer = require_role(Role.CONTRIBUTOR)


@router.get("", response_model=Page[MemoryOut])
def list_memories(
    event_id: int | None = Query(None),
    person_id: int | None = Query(None, description="Told by or mentioning"),
    inbox: bool = Query(False, description="Only memories waiting to be placed"),
    page: PageParams = Depends(),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    stmt = visible_to(scoped(Memory, user), user)
    if event_id:
        stmt = stmt.where(Memory.event_id == event_id)
    if person_id:
        mentioned = select(MemoryMention.memory_id).where(
            MemoryMention.person_id == person_id
        )
        stmt = stmt.where(
            (Memory.storyteller_id == person_id) | Memory.id.in_(mentioned)
        )
    if inbox:
        stmt = inbox_filter(stmt)
    keys = [func.coalesce(Memory.date_start, LAST_DAY), Memory.id]
    rows, cursor = paginate(db, stmt, keys, page)
    return Page(items=out(db, rows), next_cursor=cursor)


@router.post("", response_model=MemoryOut, status_code=201)
def create_memory(
    body: MemoryIn, user: User = Depends(writer), db: Session = Depends(get_session)
):
    return out(db, [create(db, user, body)])[0]


@router.get("/{memory_id}", response_model=MemoryOut)
def get_memory(
    memory_id: int, user: User = Depends(reader), db: Session = Depends(get_session)
):
    return out(db, [visible(db, memory_id, user)])[0]


@router.patch("/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: int,
    body: MemoryPatch,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    memory = visible(db, memory_id, user)
    return out(db, [apply_patch(db, user, memory, body)])[0]


@router.delete("/{memory_id}", status_code=204)
def remove_memory(
    memory_id: int, user: User = Depends(writer), db: Session = Depends(get_session)
) -> None:
    soft_delete(visible(db, memory_id, user))
    db.commit()
