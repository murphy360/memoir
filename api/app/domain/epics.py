"""Epics: arcs inside one period ("Building the house"). An epic's events follow it."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    update,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import Base, get_session
from app.core.errors import ApiError
from app.domain.common import LAST_DAY, ArchiveRow, clean, live, scoped, soft_delete
from app.domain.pagination import Page, PageParams, paginate
from app.domain.periods import Period
from app.domain.threads import Thread


class Epic(ArchiveRow, Base):
    __tablename__ = "epics"
    __table_args__ = (
        CheckConstraint("weight BETWEEN 1 AND 10", name="weight_1_10"),
        # Lets a placement name (epic, period) and have the database check they agree.
        UniqueConstraint("id", "period_id", name="uq_epics_id_period"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("periods.id", ondelete="CASCADE"), index=True
    )
    thread_id: Mapped[int | None] = mapped_column(
        ForeignKey("threads.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    weight: Mapped[int] = mapped_column(Integer, default=5)
    start_text: Mapped[str | None] = mapped_column(String(100))
    start_on: Mapped[date | None] = mapped_column(Date)
    end_text: Mapped[str | None] = mapped_column(String(100))
    end_on: Mapped[date | None] = mapped_column(Date)


class EpicIn(BaseModel):
    period_id: int
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    weight: int = Field(5, ge=1, le=10)
    thread_id: int | None = None
    start_text: str | None = Field(None, max_length=100)
    end_text: str | None = Field(None, max_length=100)


class EpicPatch(BaseModel):
    period_id: int | None = None
    title: str | None = Field(None, min_length=1, max_length=180)
    description: str | None = None
    weight: int | None = Field(None, ge=1, le=10)
    thread_id: int | None = None
    start_text: str | None = Field(None, max_length=100)
    end_text: str | None = Field(None, max_length=100)


class EpicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_id: int
    thread_id: int | None
    title: str
    description: str | None
    weight: int
    start_text: str | None
    start_on: date | None
    end_text: str | None
    end_on: date | None


def _thread(session: Session, user: User, thread_id: int | None) -> int | None:
    return live(session, Thread, thread_id, user, "thread").id if thread_id else None


def move(session: Session, user: User, epic: Epic, period_id: int) -> None:
    """Move an epic to another period of the same person; its events follow it."""
    from app.domain.participants import Participant

    target = live(session, Period, period_id, user, "period")
    current = session.get(Period, epic.period_id)
    if target.person_id != current.person_id:
        raise ApiError(
            422,
            "bad_target",
            "An epic moves only within one person's life.",
            "period_id",
        )
    epic.period_id = target.id
    session.execute(
        update(Participant)
        .where(Participant.epic_id == epic.id)
        .values(period_id=target.id)
    )


def apply_patch(session: Session, user: User, epic: Epic, body: EpicPatch) -> Epic:
    sent = body.model_fields_set
    if "period_id" in sent and body.period_id and body.period_id != epic.period_id:
        move(session, user, epic, body.period_id)
    if "thread_id" in sent:
        epic.thread_id = _thread(session, user, body.thread_id)
    if "title" in sent and body.title:
        epic.title = clean(body.title, 180)
    if "description" in sent:
        epic.description = clean(body.description, 20_000)
    if "weight" in sent and body.weight:
        epic.weight = body.weight
    for field in ("start_text", "end_text"):
        if field in sent:
            setattr(epic, field, clean(getattr(body, field), 100))
    session.commit()
    return epic


router = APIRouter(prefix="/api/epics", tags=["epics"])
reader = require_role(Role.VIEWER)
writer = require_role(Role.CONTRIBUTOR)


@router.get("", response_model=Page[EpicOut])
def list_epics(
    period_id: int = Query(...),
    page: PageParams = Depends(),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    live(db, Period, period_id, user, "period")
    stmt = scoped(Epic, user).where(Epic.period_id == period_id)
    keys = [func.coalesce(Epic.start_on, LAST_DAY), Epic.id]
    rows, cursor = paginate(db, stmt, keys, page)
    return Page(items=rows, next_cursor=cursor)


@router.post("", response_model=EpicOut, status_code=201)
def create_epic(
    body: EpicIn, user: User = Depends(writer), db: Session = Depends(get_session)
):
    period = live(db, Period, body.period_id, user, "period")
    epic = Epic(
        archive_id=user.archive_id,
        period_id=period.id,
        thread_id=_thread(db, user, body.thread_id),
        title=clean(body.title, 180),
        description=clean(body.description, 20_000),
        weight=body.weight,
        start_text=clean(body.start_text, 100),
        end_text=clean(body.end_text, 100),
    )
    db.add(epic)
    db.commit()
    return epic


@router.get("/{epic_id}", response_model=EpicOut)
def get_epic(
    epic_id: int, user: User = Depends(reader), db: Session = Depends(get_session)
):
    return live(db, Epic, epic_id, user, "epic")


@router.patch("/{epic_id}", response_model=EpicOut)
def update_epic(
    epic_id: int,
    body: EpicPatch,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    return apply_patch(db, user, live(db, Epic, epic_id, user, "epic"), body)


@router.delete("/{epic_id}", status_code=204)
def remove_epic(
    epic_id: int, user: User = Depends(writer), db: Session = Depends(get_session)
) -> None:
    """Its events stay in the period, no longer grouped."""
    from app.domain.participants import Participant

    epic = live(db, Epic, epic_id, user, "epic")
    db.execute(
        update(Participant).where(Participant.epic_id == epic.id).values(epic_id=None)
    )
    soft_delete(epic)
    db.commit()
