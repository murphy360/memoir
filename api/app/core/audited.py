"""Who made and changed a row, and soft deletion, for every table people edit.

`Audited` adds `created_by`, `updated_by`, `updated_at` and `deleted_at`. The request's
user is put on the database session (`session.info["actor_id"]`) by the auth dependency,
and a flush hook fills the columns from it, so no service has to remember to.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, event
from sqlalchemy.orm import Mapped, Session, declared_attr, mapped_column

from app.core.db import utcnow

ACTOR = "actor_id"


class Audited:
    # use_alter: users itself is Audited and archives refers to users, so these keys
    # would make a cycle for table ordering; they are added after the tables instead.
    @declared_attr
    def created_by(cls) -> Mapped[int | None]:
        return mapped_column(
            BigInteger, ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
        )

    @declared_attr
    def updated_by(cls) -> Mapped[int | None]:
        return mapped_column(
            BigInteger, ForeignKey("users.id", ondelete="SET NULL", use_alter=True)
        )

    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def act_as(session: Session, user_id: int | None) -> None:
    """Make `user_id` the author of whatever this session writes next."""
    session.info[ACTOR] = user_id


@event.listens_for(Session, "before_flush")
def _stamp(session: Session, _context, _instances) -> None:
    actor = session.info.get(ACTOR)
    now = utcnow()
    for obj in session.new:
        if isinstance(obj, Audited):
            obj.created_by = obj.created_by or actor
            obj.updated_by = actor
            obj.updated_at = now
    for obj in session.dirty:
        if isinstance(obj, Audited) and session.is_modified(obj):
            obj.updated_by = actor
            obj.updated_at = now
