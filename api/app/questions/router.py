"""The interviewer's routes: the next question, the list for you, one question."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import get_session
from app.core.errors import ApiError
from app.domain.common import live
from app.domain.memories import visible
from app.domain.questions import Question, QuestionOut
from app.questions import interviewer

router = APIRouter(prefix="/api/questions", tags=["questions"])
reader = require_role(Role.VIEWER)


class NextQuestion(BaseModel):
    question: QuestionOut | None
    waiting: bool = Field(
        False,
        description="Questions about the memory just recorded are still on their "
        "way: ask again in a moment",
    )


class QuestionsForYou(BaseModel):
    items: list[QuestionOut]


@router.get("/next", response_model=NextQuestion)
def next_question(
    after_memory_id: int | None = Query(
        None, description="The memory just recorded, whose questions should come first"
    ),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    """The one question to ask now, for the home screen and after each recording."""
    interviewer.seed(db, user)
    waiting = False
    if after_memory_id:
        try:
            waiting = interviewer.still_coming(visible(db, after_memory_id, user))
        except ApiError:
            pass  # deleted (a silent take, say): nothing to wait for
    found = interviewer.pending_for(db, user, limit=1)
    question = interviewer.out(db, found[0]) if found else None
    return NextQuestion(question=question, waiting=waiting)


@router.get("/for-you", response_model=QuestionsForYou)
def questions_for_you(user: User = Depends(reader), db: Session = Depends(get_session)):
    """Every pending question for this user, next first (at most 50)."""
    interviewer.seed(db, user)
    items = [interviewer.out(db, q) for q in interviewer.pending_for(db, user)]
    return QuestionsForYou(items=items)


@router.get("/{question_id}", response_model=QuestionOut)
def one_question(
    question_id: int, user: User = Depends(reader), db: Session = Depends(get_session)
):
    return interviewer.out(db, live(db, Question, question_id, user, "question"))
