"""Imports every model, so `Base.metadata` is complete for Alembic and the tests."""

from app.accounts.models import AuditEvent, Invitation, LoginAttempt, User, UserSession
from app.archive.models import Archive
from app.blobs.models import Blob
from app.capture.models import UploadSession
from app.domain.assets import Asset, EventAsset
from app.domain.epics import Epic
from app.domain.events import Event
from app.domain.memories import Memory, MemoryMention, MemoryPlace
from app.domain.participants import Participant
from app.domain.people import Person, PersonAlias
from app.domain.periods import Period
from app.domain.places import Place
from app.domain.questions import Question
from app.domain.settings import ArchiveSettings
from app.domain.threads import Thread
from app.jobs.models import Job, WorkerHeartbeat

__all__ = [
    "Archive",
    "ArchiveSettings",
    "Asset",
    "AuditEvent",
    "Blob",
    "Epic",
    "Event",
    "EventAsset",
    "Invitation",
    "Job",
    "LoginAttempt",
    "Memory",
    "MemoryMention",
    "MemoryPlace",
    "Participant",
    "Period",
    "Person",
    "PersonAlias",
    "Place",
    "Question",
    "Thread",
    "UploadSession",
    "User",
    "UserSession",
    "WorkerHeartbeat",
]
