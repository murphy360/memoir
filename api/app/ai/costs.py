"""One row per AI call, success or failure: which model, which prompt, how many tokens,
how long. The owner can see what Memoir's AI costs (requirements 6.1)."""

import time
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.ai.provider import Answer, Provider
from app.core.db import Base, utcnow


class AICall(Base):
    __tablename__ = "ai_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    archive_id: Mapped[int | None] = mapped_column(
        ForeignKey("archives.id", ondelete="CASCADE"), index=True
    )
    task: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(String(300))
    memory_id: Mapped[int | None] = mapped_column(
        ForeignKey("memories.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


def recorded(
    session: Session,
    provider: Provider,
    call: Callable[[], Answer],
    *,
    task: str,
    model: str,
    prompt_version: str,
    archive_id: int | None,
    memory_id: int | None = None,
) -> Answer:
    """Make the call and write its cost row (committed), whether it worked or not."""
    started = time.monotonic()
    row = AICall(
        archive_id=archive_id,
        task=task,
        provider=provider.name,
        model=model,
        prompt_version=prompt_version,
        memory_id=memory_id,
        ok=False,
    )
    try:
        answer = call()
        row.ok = True
        row.model = answer.model
        row.input_tokens, row.output_tokens = answer.input_tokens, answer.output_tokens
        return answer
    except Exception as exc:
        row.error = f"{type(exc).__name__}: {exc}"[:300]
        raise
    finally:
        row.duration_ms = int((time.monotonic() - started) * 1000)
        session.add(row)
        session.commit()
