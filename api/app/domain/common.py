"""What every domain entity shares: archive scoping, dates, soft deletion, slugs."""

import re
import unicodedata
from datetime import date
from enum import StrEnum

from sqlalchemy import BigInteger, ForeignKey, select
from sqlalchemy.orm import Mapped, Session, declared_attr, mapped_column

from app.accounts.models import User
from app.core.audited import Audited
from app.core.db import Timestamped, utcnow
from app.core.errors import ApiError


class Precision(StrEnum):
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    DECADE = "decade"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


class ArchiveRow(Audited, Timestamped):
    """A row that belongs to one archive, records who made it, and is soft-deleted."""

    @declared_attr
    def archive_id(cls) -> Mapped[int]:
        return mapped_column(
            BigInteger, ForeignKey("archives.id", ondelete="CASCADE"), index=True
        )


# Undated rows sort after every dated one.
LAST_DAY = date(9999, 12, 31)


def live(session: Session, model, row_id: int, user: User, what: str):
    """The row, if it exists in the user's archive and is not deleted; else a 404."""
    row = session.get(model, row_id)
    if row is None or row.archive_id != user.archive_id or row.deleted_at is not None:
        raise ApiError(404, "not_found", f"No such {what}.")
    return row


def scoped(model, user: User):
    """SELECT live rows of `model` in the user's archive."""
    return select(model).where(
        model.archive_id == user.archive_id, model.deleted_at.is_(None)
    )


def soft_delete(row) -> None:
    row.deleted_at = utcnow()


def slugify(text: str, fallback: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:80]
    return slug or fallback


def unique_slug(session: Session, base: str, taken) -> str:
    """`base`, or `base-2`, `base-3` and so on: the first that `taken(slug)` says is
    free.
    """
    slug, n = base, 2
    while taken(slug):
        slug, n = f"{base}-{n}", n + 1
    return slug


def clean(text: str | None, limit: int) -> str | None:
    """Trimmed text, at most `limit` characters; empty becomes None."""
    if text is None:
        return None
    text = text.strip()[:limit]
    return text or None
