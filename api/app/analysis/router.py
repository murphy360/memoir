"""Run analysis again, see whether AI is on, and what it has cost."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.ai import registry
from app.ai.costs import AICall
from app.core.db import get_session, utcnow
from app.core.settings import Settings, get_settings
from app.domain import memories
from app.domain.settings import settings_for
from app.jobs import queue

router = APIRouter(tags=["analysis"])
writer = require_role(Role.CONTRIBUTOR)


@router.post("/api/memories/{memory_id}/transcribe", response_model=memories.MemoryOut)
def transcribe_again(
    memory_id: int, user: User = Depends(writer), db: Session = Depends(get_session)
):
    """Transcribe again: after a failure, or once AI is turned on."""
    memory = memories.visible(db, memory_id, user)
    memory.transcript_state = "transcribing"
    if memory.transcript_source == "manual":
        memory.transcript_source = None
    db.commit()
    queue.enqueue(
        db, "analysis.transcribe", {"memory_id": memory.id}, requested_by=user.id
    )
    return memories.out(db, [memory])[0]


@router.post("/api/memories/{memory_id}/extract", response_model=memories.MemoryOut)
def extract_again(
    memory_id: int, user: User = Depends(writer), db: Session = Depends(get_session)
):
    memory = memories.visible(db, memory_id, user)
    memory.extraction_state = None
    db.commit()
    queue.enqueue(
        db, "analysis.extract", {"memory_id": memory.id}, requested_by=user.id
    )
    return memories.out(db, [memory])[0]


class TaskAI(BaseModel):
    task: str = Field(description="transcribe, extract or questions")
    provider: str | None = Field(description="None: no provider can do it")
    model: str | None


class AIStatus(BaseModel):
    enabled: bool
    provider: str | None = Field(description="The provider for extraction")
    model: str | None
    transcription: bool
    extraction: bool
    questions: bool
    tasks: list[TaskAI]


@router.get("/api/ai/status", response_model=AIStatus)
def ai_status(
    user: User = Depends(require_role(Role.VIEWER)),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """Whether AI is on and who does what, so the app can say "AI is off" where it
    would appear."""
    tasks = []
    for task in registry.TASKS:
        name = registry.choose(settings, task)
        model = registry.model_for(settings, task, name) if name else None
        tasks.append(TaskAI(task=task, provider=name, model=model))
    by_task = {t.task: t for t in tasks}
    switches = settings_for(db, user.archive_id)
    return AIStatus(
        enabled=any(t.provider for t in tasks),
        provider=by_task["extract"].provider,
        model=by_task["extract"].model,
        transcription=bool(by_task["transcribe"].provider)
        and switches.ai_transcription,
        extraction=bool(by_task["extract"].provider) and switches.ai_extraction,
        questions=bool(by_task["questions"].provider) and switches.ai_questions,
        tasks=tasks,
    )


class Usage(BaseModel):
    task: str
    model: str
    calls: int
    failed: int
    input_tokens: int
    output_tokens: int
    seconds: float


@router.get("/api/ai/usage", response_model=list[Usage])
def ai_usage(
    days: int = Query(30, ge=1, le=366),
    user: User = Depends(require_role(Role.OWNER)),
    db: Session = Depends(get_session),
):
    """What AI has done for this archive lately: calls, failures and tokens, by task."""
    since = utcnow() - timedelta(days=days)
    rows = db.execute(
        select(
            AICall.task,
            AICall.model,
            func.count(),
            func.count().filter(AICall.ok.is_(False)),
            func.coalesce(func.sum(AICall.input_tokens), 0),
            func.coalesce(func.sum(AICall.output_tokens), 0),
            func.coalesce(func.sum(AICall.duration_ms), 0),
        )
        .where(AICall.archive_id == user.archive_id, AICall.created_at >= since)
        .group_by(AICall.task, AICall.model)
        .order_by(AICall.task, AICall.model)
    )
    return [
        Usage(
            task=t,
            model=m,
            calls=c,
            failed=f,
            input_tokens=i,
            output_tokens=o,
            seconds=round(ms / 1000, 1),
        )
        for t, m, c, f, i, o, ms in rows
    ]
