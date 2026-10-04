"""Upload sessions: open, append a chunk at an offset, finalize into a memory, abort.

Chunks land in a part file under the blob root's `uploads/`. A chunk at the wrong offset
is refused with the offset the server has, so a client that lost track (a reload, a
dropped connection) resumes exactly there. Finalizing twice returns the same memory.
"""

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.accounts.models import User
from app.blobs.store import BlobStore
from app.capture.models import UploadSession
from app.core.db import utcnow
from app.core.errors import ApiError
from app.core.settings import Settings
from app.domain.common import live
from app.domain.events import Event
from app.domain.memories import Memory, MemoryMention, join_event
from app.domain.people import Person
from app.domain.periods import Period
from app.domain.questions import Question
from app.jobs import queue

MAX_CHUNK = 8 * 1024 * 1024
AUDIO_TYPES = ("audio/", "video/webm", "video/mp4")


def part_path(settings: Settings, session_id: str) -> Path:
    return Path(settings.blob_root) / "uploads" / f"{session_id}.part"


def _check_context(session: Session, user: User, context: dict) -> dict:
    refs = {"event_id": Event, "period_id": Period, "person_id": Person}
    refs["question_id"] = Question
    clean = {}
    for key, model in refs.items():
        if context.get(key):
            clean[key] = live(session, model, int(context[key]), user, key[:-3]).id
    if context.get("quick"):
        clean["quick"] = True
    return clean


def open_session(
    session: Session, user: User, content_type: str, context: dict, settings: Settings
) -> UploadSession:
    if not content_type.startswith(AUDIO_TYPES):
        raise ApiError(415, "not_audio", "Only recordings can be uploaded here.")
    row = UploadSession(
        id=str(uuid.uuid4()),
        archive_id=user.archive_id,
        user_id=user.id,
        content_type=content_type[:120],
        context=_check_context(session, user, context),
    )
    part = part_path(settings, row.id)
    part.parent.mkdir(parents=True, exist_ok=True)
    part.touch()
    session.add(row)
    session.commit()
    return row


def mine(session: Session, user: User, session_id: str) -> UploadSession:
    row = session.get(UploadSession, session_id)
    if row is None or row.user_id != user.id:
        raise ApiError(404, "not_found", "No such upload.")
    return row


def append(
    session: Session, row: UploadSession, offset: int, data: bytes, settings: Settings
) -> UploadSession:
    """Add a chunk. A chunk already received is accepted and ignored; a gap
    is refused.
    """
    if row.status != "open":
        raise ApiError(409, "upload_closed", "This upload is already finished.")
    if len(data) > MAX_CHUNK:
        raise ApiError(
            413, "chunk_too_big", "Send the recording in pieces of 8 MB or less."
        )
    if offset + len(data) <= row.received_bytes:
        return row
    if offset != row.received_bytes:
        raise ApiError(
            409,
            "wrong_offset",
            f"The server has {row.received_bytes} bytes; continue from there.",
        )
    with part_path(settings, row.id).open("ab") as out:
        out.write(data)
    row.received_bytes += len(data)
    row.updated_at = utcnow()
    session.commit()
    return row


def _storyteller(session: Session, user: User) -> int | None:
    from sqlalchemy import select

    return session.scalars(
        select(Person.id).where(Person.user_id == user.id, Person.deleted_at.is_(None))
    ).first()


def finalize(
    session: Session, user: User, row: UploadSession, settings: Settings
) -> Memory:
    """Turn the received bytes into the original-audio blob and a memory, and queue the
    normalisation. Finalizing an already finished upload returns its memory."""
    if row.status == "finalized":
        return session.get(Memory, row.memory_id)
    if row.status != "open" or row.received_bytes == 0:
        raise ApiError(409, "nothing_uploaded", "Nothing was uploaded.")
    part = part_path(settings, row.id)
    store = BlobStore(settings.blob_root)
    with part.open("rb") as f:
        blob = store.put(
            session, iter(lambda: f.read(1024 * 1024), b""), row.content_type
        )
    memory = _memory(session, user, row, blob.sha256)
    row.status, row.memory_id = "finalized", memory.id
    session.commit()
    part.unlink(missing_ok=True)
    queue.enqueue(
        session,
        "capture.normalize_audio",
        {"memory_id": memory.id},
        idempotency_key=f"normalize:{memory.id}",
        requested_by=user.id,
    )
    return memory


def _memory(session: Session, user: User, row: UploadSession, original: str) -> Memory:
    context = row.context or {}
    memory = Memory(
        archive_id=user.archive_id,
        uploaded_by=user.id,
        storyteller_id=_storyteller(session, user),
        event_id=context.get("event_id"),
        response_to_question_id=context.get("question_id"),
        original_audio_sha256=original,
        audio_state="normalising",
        capture_context=context,
    )
    session.add(memory)
    session.flush()
    if context.get("person_id") and context["person_id"] != memory.storyteller_id:
        session.add(MemoryMention(memory_id=memory.id, person_id=context["person_id"]))
        session.flush()
    join_event(session, memory)
    return memory


def abort(session: Session, row: UploadSession, settings: Settings) -> None:
    if row.status == "open":
        row.status = "aborted"
        session.commit()
        part_path(settings, row.id).unlink(missing_ok=True)
