"""Archive settings (requirements 3.4): what the owner may change without a deploy.
Secrets are never settings; they stay in the environment."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.archive.models import Archive
from app.core.audited import Audited
from app.core.db import Base, get_session
from app.core.errors import ApiError


class ArchiveSettings(Audited, Base):
    __tablename__ = "archive_settings"

    archive_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("archives.id", ondelete="CASCADE"), primary_key=True
    )
    # What the app calls the person the memoir is about ("Grandma's Memoir").
    storyteller_name: Mapped[str | None] = mapped_column(String(120))
    ai_transcription: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_extraction: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_questions: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_research: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_photos: Mapped[bool] = mapped_column(Boolean, default=True)
    face_detection_on_upload: Mapped[bool] = mapped_column(Boolean, default=True)
    face_auto_assign_threshold: Mapped[float] = mapped_column(Float, default=0.92)
    # A one-tap quick memory is filed where the system suggests, with "Saved to".
    auto_file_quick_memories: Mapped[bool] = mapped_column(Boolean, default=True)


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    archive_name: str = ""
    time_zone: str = "UTC"
    storyteller_name: str | None
    ai_transcription: bool
    ai_extraction: bool
    ai_questions: bool
    ai_research: bool
    ai_photos: bool
    face_detection_on_upload: bool
    face_auto_assign_threshold: float
    auto_file_quick_memories: bool


class SettingsPatch(BaseModel):
    archive_name: str | None = Field(None, min_length=1, max_length=160)
    time_zone: str | None = Field(None, max_length=64)
    storyteller_name: str | None = Field(None, max_length=120)
    ai_transcription: bool | None = None
    ai_extraction: bool | None = None
    ai_questions: bool | None = None
    ai_research: bool | None = None
    ai_photos: bool | None = None
    face_detection_on_upload: bool | None = None
    face_auto_assign_threshold: float | None = Field(None, ge=0.5, le=1.0)
    auto_file_quick_memories: bool | None = None


def settings_for(session: Session, archive_id: int) -> ArchiveSettings:
    row = session.get(ArchiveSettings, archive_id)
    if row is None:
        row = ArchiveSettings(
            archive_id=archive_id,
            ai_transcription=True,
            ai_extraction=True,
            ai_questions=True,
            ai_research=True,
            ai_photos=True,
            face_detection_on_upload=True,
            face_auto_assign_threshold=0.92,
            auto_file_quick_memories=True,
        )
        session.add(row)
        session.commit()
    return row


def _out(session: Session, user: User) -> SettingsOut:
    archive = session.get(Archive, user.archive_id)
    row = settings_for(session, user.archive_id)
    return SettingsOut.model_validate(row).model_copy(
        update={"archive_name": archive.name, "time_zone": archive.time_zone}
    )


def _zone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ApiError(
            422, "bad_time_zone", "Use a time zone like America/New_York.", "time_zone"
        ) from exc
    return name


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def read_settings(
    user: User = Depends(require_role(Role.VIEWER)), db: Session = Depends(get_session)
):
    return _out(db, user)


@router.patch("", response_model=SettingsOut)
def change_settings(
    body: SettingsPatch,
    user: User = Depends(require_role(Role.OWNER)),
    db: Session = Depends(get_session),
):
    archive = db.get(Archive, user.archive_id)
    row = settings_for(db, user.archive_id)
    for field in body.model_fields_set:
        value = getattr(body, field)
        if field == "archive_name" and value:
            archive.name = value.strip()
        elif field == "time_zone" and value:
            archive.time_zone = _zone(value)
        elif field not in ("archive_name", "time_zone") and (
            value is not None or field == "storyteller_name"
        ):
            setattr(row, field, value)
    db.commit()
    return _out(db, user)
