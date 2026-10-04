"""Periods: the chapters of one person's life. Every period belongs to exactly one
person.
"""

from datetime import date
from enum import StrEnum

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
    update,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import Base, get_session, utcnow
from app.core.errors import ApiError
from app.domain.common import (
    LAST_DAY,
    ArchiveRow,
    clean,
    live,
    scoped,
    slugify,
    soft_delete,
    unique_slug,
)
from app.domain.pagination import Page, PageParams, paginate
from app.domain.people import Person


class Period(ArchiveRow, Base):
    __tablename__ = "periods"
    __table_args__ = (
        # Lets a participant's placement name (period, person) and have the database
        # check that the period is that person's own.
        UniqueConstraint("id", "person_id", name="uq_periods_id_person"),
        Index(
            "uq_periods_person_slug",
            "person_id",
            "slug",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(100))
    start_text: Mapped[str | None] = mapped_column(String(100))
    start_on: Mapped[date | None] = mapped_column(Date)
    end_text: Mapped[str | None] = mapped_column(String(100))
    end_on: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    # True when the summary was written by the machine; a typed one is never replaced.
    summary_generated: Mapped[bool] = mapped_column(Boolean, default=False)


class PeriodIn(BaseModel):
    person_id: int
    title: str = Field(min_length=1, max_length=160)
    start_text: str | None = Field(None, max_length=100)
    end_text: str | None = Field(None, max_length=100)
    summary: str | None = None


class PeriodPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=160)
    start_text: str | None = Field(None, max_length=100)
    end_text: str | None = Field(None, max_length=100)
    summary: str | None = None


class PeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    person_id: int
    title: str
    slug: str
    start_text: str | None
    start_on: date | None
    end_text: str | None
    end_on: date | None
    summary: str | None
    summary_generated: bool


class Children(StrEnum):
    MOVE = "move"
    UNASSIGN = "unassign"


class PeriodDeleted(BaseModel):
    """What deleting a period did, so the app can say it in plain words."""

    epics_moved: int = 0
    epics_removed: int = 0
    placements_moved: int = 0
    placements_unassigned: int = 0


def _slug(session: Session, person_id: int, title: str, me: int | None = None) -> str:
    def taken(slug: str) -> bool:
        clash = session.scalars(
            select(Period.id).where(
                Period.person_id == person_id,
                Period.slug == slug,
                Period.deleted_at.is_(None),
            )
        ).first()
        return clash is not None and clash != me

    return unique_slug(session, slugify(title, "period"), taken)


def create(session: Session, user: User, body: PeriodIn) -> Period:
    person = live(session, Person, body.person_id, user, "person")
    title = clean(body.title, 160) or "Untitled"
    period = Period(
        archive_id=user.archive_id,
        person_id=person.id,
        title=title,
        slug=_slug(session, person.id, title),
        start_text=clean(body.start_text, 100),
        end_text=clean(body.end_text, 100),
        summary=clean(body.summary, 20_000),
    )
    session.add(period)
    session.commit()
    return period


def counts(session: Session, period: Period) -> tuple[int, int]:
    """(live epics, participant placements) in a period."""
    from app.domain.epics import Epic
    from app.domain.participants import Participant

    epics = session.scalar(
        select(func.count())
        .select_from(Epic)
        .where(Epic.period_id == period.id, Epic.deleted_at.is_(None))
    )
    placed = session.scalar(
        select(func.count())
        .select_from(Participant)
        .where(Participant.period_id == period.id)
    )
    return epics, placed


def remove(
    session: Session,
    user: User,
    period: Period,
    children: Children | None,
    move_to: int | None,
) -> PeriodDeleted:
    """Delete a period, after doing with its epics and events what the user chose.

    Move: epics and placements go to another of the same person's periods.
    Unassign: the epics are removed with the period and their events go to the inbox.
    With children and no choice, nothing happens and the app is told to ask.
    """
    epics, placed = counts(session, period)
    if (epics or placed) and children is None:
        raise ApiError(
            409,
            "period_has_children",
            f"This period holds {epics} epics and {placed} placed events. "
            "Move them to another period or unassign them.",
        )
    if children == Children.MOVE:
        target = _move_target(session, user, period, move_to)
        done = move_contents(session, period, target)
    else:
        done = _unassign_contents(session, period)
    soft_delete(period)
    session.commit()
    return done


def _move_target(session: Session, user: User, period: Period, move_to: int | None):
    target = live(session, Period, move_to or 0, user, "period") if move_to else None
    if target is None or target.person_id != period.person_id or target.id == period.id:
        raise ApiError(
            422,
            "bad_target",
            "Choose another period of the same person.",
            "move_to",
        )
    return target


def move_contents(session: Session, source: Period, target: Period) -> PeriodDeleted:
    """Every epic and placement of `source` moves to `target` (same person)."""
    from app.domain.epics import Epic
    from app.domain.participants import Participant

    epics = session.execute(
        update(Epic)
        .where(Epic.period_id == source.id, Epic.deleted_at.is_(None))
        .values(period_id=target.id)
    ).rowcount
    placed = session.execute(
        update(Participant)
        .where(Participant.period_id == source.id)
        .values(period_id=target.id)
    ).rowcount
    return PeriodDeleted(epics_moved=epics, placements_moved=placed)


def _unassign_contents(session: Session, period: Period) -> PeriodDeleted:
    from app.domain.epics import Epic
    from app.domain.participants import Participant

    placed = session.execute(
        update(Participant)
        .where(Participant.period_id == period.id)
        .values(period_id=None, epic_id=None)
    ).rowcount
    epics = session.execute(
        update(Epic)
        .where(Epic.period_id == period.id, Epic.deleted_at.is_(None))
        .values(deleted_at=utcnow())
    ).rowcount
    return PeriodDeleted(epics_removed=epics, placements_unassigned=placed)


def soft_delete_periods_of(session: Session, person_id: int) -> None:
    """With a person: their periods and the periods' epics. Their placements stay
    attached to them (and come back if the person is restored)."""
    from app.domain.epics import Epic

    now = utcnow()
    ids = select(Period.id).where(Period.person_id == person_id)
    session.execute(
        update(Epic)
        .where(Epic.period_id.in_(ids), Epic.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    session.execute(
        update(Period)
        .where(Period.person_id == person_id, Period.deleted_at.is_(None))
        .values(deleted_at=now)
    )


router = APIRouter(prefix="/api/periods", tags=["periods"])
reader = require_role(Role.VIEWER)
writer = require_role(Role.CONTRIBUTOR)


@router.get("", response_model=Page[PeriodOut])
def list_periods(
    person_id: int = Query(..., description="Whose chapters"),
    page: PageParams = Depends(),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    live(db, Person, person_id, user, "person")
    stmt = scoped(Period, user).where(Period.person_id == person_id)
    keys = [func.coalesce(Period.start_on, LAST_DAY), Period.id]
    rows, cursor = paginate(db, stmt, keys, page)
    return Page(items=rows, next_cursor=cursor)


@router.post("", response_model=PeriodOut, status_code=201)
def create_period(
    body: PeriodIn, user: User = Depends(writer), db: Session = Depends(get_session)
):
    return create(db, user, body)


@router.get("/{period_id}", response_model=PeriodOut)
def get_period(
    period_id: int, user: User = Depends(reader), db: Session = Depends(get_session)
):
    return live(db, Period, period_id, user, "period")


@router.patch("/{period_id}", response_model=PeriodOut)
def update_period(
    period_id: int,
    body: PeriodPatch,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    period = live(db, Period, period_id, user, "period")
    sent = body.model_fields_set
    if "title" in sent and body.title:
        period.title = clean(body.title, 160)
        period.slug = _slug(db, period.person_id, period.title, period.id)
    for field in ("start_text", "end_text"):
        if field in sent:
            setattr(period, field, clean(getattr(body, field), 100))
    if "summary" in sent:
        period.summary = clean(body.summary, 20_000)
        period.summary_generated = False
    db.commit()
    return period


@router.delete("/{period_id}", response_model=PeriodDeleted)
def remove_period(
    period_id: int,
    children: Children | None = Query(None, description="What to do with its contents"),
    move_to: int | None = Query(None, description="With children=move: the period"),
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    period = live(db, Period, period_id, user, "period")
    return remove(db, user, period, children, move_to)
