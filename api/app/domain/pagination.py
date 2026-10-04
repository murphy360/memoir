"""Cursor pagination: every list endpoint answers a page and a cursor for the next one.

The cursor is the sort key of the last row, so a page never repeats or skips a row when
others are added meanwhile. It is opaque to clients: base64 of a small JSON list.
"""

import base64
import json
from datetime import date
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import ApiError

T = TypeVar("T")
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class PageParams:
    """The `cursor` and `limit` query parameters, shared by every list."""

    def __init__(
        self,
        cursor: str | None = Query(None, description="From the previous page"),
        limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    ):
        self.cursor, self.limit = cursor, limit


def _encode(values) -> str:
    plain = [f"D:{v.isoformat()}" if isinstance(v, date) else v for v in values]
    return base64.urlsafe_b64encode(json.dumps(plain).encode()).decode()


def _decode(cursor: str) -> list:
    try:
        plain = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except ValueError as exc:
        raise ApiError(400, "bad_cursor", "That page cursor is not valid.") from exc
    if not isinstance(plain, list):
        raise ApiError(400, "bad_cursor", "That page cursor is not valid.")
    return [
        date.fromisoformat(v[2:]) if isinstance(v, str) and v.startswith("D:") else v
        for v in plain
    ]


def paginate(session: Session, stmt: Select, keys: list, params: PageParams):
    """Run `stmt` (a select of one entity) ordered by `keys`; returns (rows, cursor)."""
    if params.cursor:
        values = _decode(params.cursor)
        if len(values) != len(keys):
            raise ApiError(400, "bad_cursor", "That page cursor is not valid.")
        stmt = stmt.where(tuple_(*keys) > tuple_(*values))
    rows = session.execute(
        stmt.add_columns(*keys).order_by(*keys).limit(params.limit + 1)
    ).all()
    more = len(rows) > params.limit
    rows = rows[: params.limit]
    cursor = _encode(rows[-1][1:]) if more and rows else None
    return [r[0] for r in rows], cursor
