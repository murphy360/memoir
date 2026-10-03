"""The turn-based interviewer: which question comes next for a person, the seed
questions for an archive that has none, and whether a just-recorded memory's own
questions are still on their way.

Next means: questions from the most recently recorded memory first (what was just
said), then by scope (the event, its period, a person, then general), then the oldest.
A question is for the storyteller of the memory it came from, or for anyone.
"""

from datetime import timedelta

from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.core.db import utcnow
from app.domain.common import scoped
from app.domain.events import Event
from app.domain.memories import Memory, visible_to
from app.domain.people import Person
from app.domain.periods import Period
from app.domain.questions import Question, QuestionIn, QuestionOut, Scope, Status, add

SEEDS = (
    "What should we call you?",
    "Where and when were you born?",
    "Tell me about your parents.",
)
SCOPE_ORDER = {Scope.EVENT: 0, Scope.PERIOD: 1, Scope.PERSON: 2}
# How long after a recording its own questions are worth waiting for.
PATIENCE = timedelta(minutes=3)
# States after which a memory's questions will not come.
NO_QUESTIONS = {"failed", "ai_off", "needs_details"}


def own_person_id(session: Session, user: User) -> int | None:
    return session.scalars(
        select(Person.id).where(Person.user_id == user.id, Person.deleted_at.is_(None))
    ).first()


def seed(session: Session, user: User) -> None:
    """The first questions, for an archive that never had one. Once only, so dismissed
    seed questions stay dismissed."""
    asked = session.scalars(
        select(Question.id).where(Question.archive_id == user.archive_id)
    ).first()
    if asked is None:
        for text in SEEDS:
            add(session, user, QuestionIn(text=text))


def pending_for(session: Session, user: User, limit: int = 50) -> list[Question]:
    """The user's pending questions, next first."""
    me = own_person_id(session, user)
    rank = case(
        {k.value: v for k, v in SCOPE_ORDER.items()}, value=Question.scope, else_=3
    )
    seen = visible_to(select(Memory.id), user)
    stmt = (
        scoped(Question, user)
        .outerjoin(Memory, Memory.id == Question.source_memory_id)
        .where(
            Question.status == Status.PENDING,
            or_(Question.asked_of_id.is_(None), Question.asked_of_id == me),
            or_(
                Question.source_memory_id.is_(None),
                and_(Memory.deleted_at.is_(None), Memory.id.in_(seen)),
            ),
        )
        .order_by(
            Memory.created_at.desc().nulls_last(),
            rank,
            Question.created_at,
            Question.id,
        )
        .limit(limit)
    )
    return list(session.scalars(stmt))


def about(session: Session, question: Question) -> str | None:
    """What the question asks about, in a few words."""
    targets = (
        (question.event_id, Event, "title"),
        (question.period_id, Period, "title"),
        (question.person_id, Person, "name"),
        (question.source_memory_id, Memory, "title"),
    )
    for ref, model, field in targets:
        row = session.get(model, ref) if ref else None
        if row is not None and row.deleted_at is None and getattr(row, field):
            return getattr(row, field)
    return None


def out(session: Session, question: Question) -> QuestionOut:
    shown = QuestionOut.model_validate(question)
    return shown.model_copy(update={"about": about(session, question)})


def still_coming(memory: Memory) -> bool:
    """Whether the memory's own questions may still arrive: worth waiting a moment."""
    if memory.questions_state or memory.deleted_at is not None:
        return False
    if {memory.transcript_state, memory.extraction_state} & NO_QUESTIONS:
        return False
    return utcnow() - memory.created_at < PATIENCE
