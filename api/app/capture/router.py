"""The upload routes, and the route that plays a memory's recording."""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.blobs.models import Blob
from app.blobs.store import BlobStore
from app.capture import service
from app.core.db import get_session
from app.core.errors import ApiError
from app.core.settings import Settings, get_settings
from app.domain import memories

router = APIRouter(tags=["capture"])
writer = require_role(Role.CONTRIBUTOR)
reader = require_role(Role.VIEWER)


class Context(BaseModel):
    """Where the recording was started: it travels with the upload."""

    event_id: int | None = None
    period_id: int | None = None
    person_id: int | None = None
    question_id: int | None = None
    quick: bool = Field(False, description="One tap from the home screen")


class OpenUpload(BaseModel):
    content_type: str = Field(max_length=120, examples=["audio/webm;codecs=opus"])
    context: Context = Context()


class UploadOut(BaseModel):
    id: str
    received_bytes: int
    status: str
    memory_id: int | None


def _out(row) -> UploadOut:
    return UploadOut(
        id=row.id,
        received_bytes=row.received_bytes,
        status=row.status,
        memory_id=row.memory_id,
    )


@router.post("/api/capture/uploads", response_model=UploadOut, status_code=201)
def open_upload(
    body: OpenUpload,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    context = body.context.model_dump(exclude_none=True)
    return _out(service.open_session(db, user, body.content_type, context, settings))


@router.get("/api/capture/uploads/{upload_id}", response_model=UploadOut)
def upload_state(
    upload_id: str, user: User = Depends(writer), db: Session = Depends(get_session)
):
    """How far an upload got: a client resumes from `received_bytes`."""
    return _out(service.mine(db, user, upload_id))


@router.put("/api/capture/uploads/{upload_id}", response_model=UploadOut)
async def upload_chunk(
    upload_id: str,
    request: Request,
    offset: int = Query(..., ge=0, description="Where this chunk starts"),
    user: User = Depends(writer),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """The request body is the chunk's raw bytes (application/octet-stream)."""
    data = await request.body()
    row = await run_in_threadpool(service.mine, db, user, upload_id)
    row = await run_in_threadpool(service.append, db, row, offset, data, settings)
    return _out(row)


@router.post(
    "/api/capture/uploads/{upload_id}/finalize", response_model=memories.MemoryOut
)
def finalize_upload(
    upload_id: str,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    memory = service.finalize(db, user, service.mine(db, user, upload_id), settings)
    return memories.out(db, [memory])[0]


@router.delete("/api/capture/uploads/{upload_id}", status_code=204)
def abort_upload(
    upload_id: str,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> None:
    service.abort(db, service.mine(db, user, upload_id), settings)


@router.get("/api/memories/{memory_id}/audio", response_class=FileResponse)
def memory_audio(
    memory_id: int,
    original: bool = Query(False, description="The recording as it was made"),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """The recording, MP3 when normalised. Supports Range requests, so
    players can seek.
    """
    memory = memories.visible(db, memory_id, user)
    sha = (
        memory.original_audio_sha256
        if original
        else (memory.audio_sha256 or memory.original_audio_sha256)
    )
    if sha is None:
        raise ApiError(404, "no_audio", "This memory has no recording.")
    blob = db.get(Blob, sha)
    return FileResponse(
        BlobStore(settings.blob_root).path(sha), media_type=blob.content_type
    )
