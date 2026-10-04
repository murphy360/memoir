"""Questions: follow-up prompts for the storytellers. A pending question's text is
unique within the archive (compared without case or extra spaces), whatever made it.
"""

import re
from enum import StrEnum

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import Base, get_session
from app.core.errors import ApiError
from app.domain.common import ArchiveRow, live, scoped, soft_delete
from app.domain.events import Event
from app.domain.pagination import Page, PageParams, paginate
from app.domain.people import Person
from app.domain.periods import Period


class Status(StrEnum):
    PENDING = "pending"
    ANSWERED = "answered"
    DISMISSED = "dismissed"


class Scope(StrEnum):
    GENERAL = "general"
    PERIOD = "period"
    EVENT = "event"
    PERSON = "person"


class Question(ArchiveRow, Base):
    __tablename__ = "questions"
    __table_args__ = (
        Index(
            "uq_questions_pending_text",
            "archive_id",
            "normalized",
            unique=True,
            postgresql_where="status = 'pending' AND deleted_at IS NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    normalized: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=Status.PENDING, index=True)
    scope: Mapped[str] = mapped_column(String(16), default=Scope.GENERAL)
    source_memory_id: Mapped[int | None] = mapped_column(
        ForeignKey("memories.id", ondelete="SET NULL")
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL")
    )
    period_id: Mapped[int | None] = mapped_column(
        ForeignKey("periods.id", ondelete="SET NULL")
    )
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("people.id", ondelete="SET NULL")
    )
    answered_by_memory_id: Mapped[int | None] = mapped_column(
        ForeignKey("memories.id", ondelete="SET NULL")
    )


class QuestionIn(BaseModel):
    text: str = Field(min_length=3, max_length=1000)
    scope: Scope = Scope.GENERAL
    event_id: int | None = None
    period_id: int | None = None
    person_id: int | None = None


class QuestionPatch(BaseModel):
    status: Status
    answered_by_memory_id: int | None = None


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    status: Status
    scope: Scope
    source_memory_id: int | None
    event_id: int | None
    period_id: int | None
    person_id: int | None
    answered_by_memory_id: int | None


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _check_scope(session: Session, user: User, body: QuestionIn) -> None:
    refs = {Scope.EVENT: (Event, body.event_id), Scope.PERIOD: (Period, body.period_id)}
    refs[Scope.PERSON] = (Person, body.person_id)
    if body.scope in refs:
        model, ref = refs[body.scope]
        if not ref:
            raise ApiError(
                422,
                "scope_needs_target",
                f"A {body.scope} question needs its {body.scope}.",
            )
        live(session, model, ref, user, body.scope)


def add(
    session: Session, user: User, body: QuestionIn, source_memory_id: int | None = None
):
    """Add a pending question; an identical pending one is returned instead."""
    _check_scope(session, user, body)
    key = normalize(body.text)
    same = session.scalars(
        scoped(Question, user).where(
            Question.normalized == key, Question.status == Status.PENDING
        )
    ).first()
    if same:
        return same
    question = Question(
        archive_id=user.archive_id,
        text=body.text.strip(),
        normalized=key,
        scope=body.scope,
        event_id=body.event_id,
        period_id=body.period_id,
        person_id=body.person_id,
        source_memory_id=source_memory_id,
    )
    session.add(question)
    session.commit()
    return question


router = APIRouter(prefix="/api/questions", tags=["questions"])
reader = require_role(Role.VIEWER)
writer = require_role(Role.CONTRIBUTOR)


@router.get("", response_model=Page[QuestionOut])
def list_questions(
    status: Status = Query(Status.PENDING),
    scope: Scope | None = Query(None),
    event_id: int | None = Query(None),
    person_id: int | None = Query(None),
    page: PageParams = Depends(),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    stmt = scoped(Question, user).where(Question.status == status)
    if scope:
        stmt = stmt.where(Question.scope == scope)
    if event_id:
        stmt = stmt.where(Question.event_id == event_id)
    if person_id:
        stmt = stmt.where(Question.person_id == person_id)
    rows, cursor = paginate(db, stmt, [Question.created_at, Question.id], page)
    return Page(items=rows, next_cursor=cursor)


@router.post("", response_model=QuestionOut, status_code=201)
def ask(
    body: QuestionIn, user: User = Depends(writer), db: Session = Depends(get_session)
):
    return add(db, user, body)


@router.patch("/{question_id}", response_model=QuestionOut)
def answer_or_dismiss(
    question_id: int,
    body: QuestionPatch,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    from app.domain.memories import visible

    question = live(db, Question, question_id, user, "question")
    if body.answered_by_memory_id:
        visible(db, body.answered_by_memory_id, user)
    question.status = body.status
    question.answered_by_memory_id = body.answered_by_memory_id
    db.commit()
    return question


@router.delete("/{question_id}", status_code=204)
def remove_question(
    question_id: int, user: User = Depends(writer), db: Session = Depends(get_session)
) -> None:
    soft_delete(live(db, Question, question_id, user, "question"))
    db.commit()


def first_pending(session: Session, user: User) -> Question | None:
    return session.scalars(
        scoped(Question, user)
        .where(Question.status == Status.PENDING)
        .order_by(Question.created_at, Question.id)
    ).first()
