"""Threads: themes across time ("Faith", "The farm"). They tag epics and events only."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Index, String, Text, func, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import Base, get_session
from app.core.errors import ApiError
from app.domain.common import (
    ArchiveRow,
    clean,
    live,
    scoped,
    slugify,
    soft_delete,
    unique_slug,
)
from app.domain.pagination import Page, PageParams, paginate


class Thread(ArchiveRow, Base):
    __tablename__ = "threads"
    __table_args__ = (
        Index(
            "uq_threads_archive_title",
            "archive_id",
            func.lower("title"),
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        Index(
            "uq_threads_archive_slug",
            "archive_id",
            "slug",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str | None] = mapped_column(Text)


class ThreadIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    summary: str | None = None


class ThreadPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=160)
    summary: str | None = None


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: str
    summary: str | None


def _check_title(session: Session, user: User, title: str, me: int | None) -> str:
    title = clean(title, 160) or ""
    other = session.scalars(
        scoped(Thread, user).where(func.lower(Thread.title) == title.lower())
    ).first()
    if not title or (other and other.id != me):
        raise ApiError(
            409, "title_taken", "There is already a thread by that name.", "title"
        )
    return title


def _slug(session: Session, user: User, title: str) -> str:
    def taken(slug: str) -> bool:
        return (
            session.scalars(scoped(Thread, user).where(Thread.slug == slug)).first()
            is not None
        )

    return unique_slug(session, slugify(title, "thread"), taken)


router = APIRouter(prefix="/api/threads", tags=["threads"])
reader = require_role(Role.VIEWER)
writer = require_role(Role.CONTRIBUTOR)


@router.get("", response_model=Page[ThreadOut])
def list_threads(
    page: PageParams = Depends(),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    keys = [func.lower(Thread.title), Thread.id]
    rows, cursor = paginate(db, scoped(Thread, user), keys, page)
    return Page(items=rows, next_cursor=cursor)


@router.post("", response_model=ThreadOut, status_code=201)
def create_thread(
    body: ThreadIn, user: User = Depends(writer), db: Session = Depends(get_session)
):
    title = _check_title(db, user, body.title, None)
    thread = Thread(
        archive_id=user.archive_id,
        title=title,
        slug=_slug(db, user, title),
        summary=clean(body.summary, 10_000),
    )
    db.add(thread)
    db.commit()
    return thread


@router.get("/{thread_id}", response_model=ThreadOut)
def get_thread(
    thread_id: int, user: User = Depends(reader), db: Session = Depends(get_session)
):
    return live(db, Thread, thread_id, user, "thread")


@router.patch("/{thread_id}", response_model=ThreadOut)
def update_thread(
    thread_id: int,
    body: ThreadPatch,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    thread = live(db, Thread, thread_id, user, "thread")
    if "title" in body.model_fields_set and body.title:
        thread.title = _check_title(db, user, body.title, thread.id)
    if "summary" in body.model_fields_set:
        thread.summary = clean(body.summary, 10_000)
    db.commit()
    return thread


@router.delete("/{thread_id}", status_code=204)
def remove_thread(
    thread_id: int, user: User = Depends(writer), db: Session = Depends(get_session)
) -> None:
    """Untag every epic and event, then soft-delete the thread. Nothing else
    is deleted.
    """
    from app.domain.epics import Epic
    from app.domain.events import Event

    thread = live(db, Thread, thread_id, user, "thread")
    for model in (Epic, Event):
        db.execute(
            update(model).where(model.thread_id == thread.id).values(thread_id=None)
        )
    soft_delete(thread)
    db.commit()
