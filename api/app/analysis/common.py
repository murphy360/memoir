"""What both analysis jobs need: the memory, its uploader, and whether AI is on."""

from sqlalchemy.orm import Session

from app.accounts.models import User
from app.ai import registry
from app.ai.provider import Provider
from app.core.settings import Settings, get_settings
from app.domain.memories import Memory
from app.domain.settings import settings_for
from app.jobs.registry import PermanentError


def load(session: Session, memory_id: int) -> Memory:
    memory = session.get(Memory, memory_id)
    if memory is None or memory.deleted_at is not None:
        raise PermanentError(f"memory {memory_id} is gone")
    return memory


def acting_user(session: Session, memory: Memory) -> User:
    """Names resolve within the memory's archive, as the person who recorded it."""
    user = session.get(User, memory.uploaded_by) if memory.uploaded_by else None
    if user is None:
        user = session.query(User).filter(User.archive_id == memory.archive_id).first()
    return user


def ai_for(
    session: Session, memory: Memory, switch: str, task: str
) -> tuple[Provider | None, Settings]:
    """The task's provider, or None when no provider can do it or the owner turned
    this task off."""
    settings = get_settings()
    if not getattr(settings_for(session, memory.archive_id), switch):
        return None, settings
    return registry.provider(settings, task), settings
