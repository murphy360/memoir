"""Putting a reading on a row, and the rule that a person's date is never overwritten.

Every dated column group has a `*_source`: `manual` when a person typed it, otherwise
the name of what set it (`transcript`, `exif`, `research`). A job calls `set_by_job`,
which leaves a manual date alone.
"""

from datetime import date

from app.core.errors import ApiError
from app.dates.grammar import EXAMPLES, NOW, Reading, parse

MANUAL = "manual"


def unreadable(field: str) -> ApiError:
    return ApiError(
        422,
        "unreadable_date",
        "Could not read this date. Try one like: " + "; ".join(EXAMPLES[:6]) + ".",
        field,
    )


def read(text: str | None, field: str, keep_text_only: bool) -> Reading | None:
    """The reading of `text`; a 422 when it has none, unless the text is to be kept as
    is.
    """
    if not text or not text.strip():
        return None
    found = parse(text)
    if found is None and not keep_text_only:
        raise unreadable(field)
    return found


def set_point(row, prefix: str, text: str | None, source: str, keep: bool = False):
    """A single date (events, memories, assets, birth, death): text,
    range, precision.
    """
    text = text.strip()[:100] if text and text.strip() else None
    found = read(text, f"{prefix}_text", keep)
    setattr(row, f"{prefix}_text", text)
    setattr(row, f"{prefix}_start", found.start if found else None)
    setattr(row, f"{prefix}_end", found.end if found else None)
    if hasattr(row, f"{prefix}_precision"):
        setattr(row, f"{prefix}_precision", found.precision if found else None)
    setattr(row, f"{prefix}_source", source if text else None)
    return found


def _end_of(text: str | None, found: Reading | None) -> date | None:
    if text and NOW.match(text.strip().lower()):
        return date.today()
    return found.end if found else None


def set_range(row, start_text, end_text, source: str, keep: bool = False) -> None:
    """A period or an epic: when it began and when it ended ("now" for still going)."""
    start_text = start_text.strip()[:100] if start_text and start_text.strip() else None
    end_text = end_text.strip()[:100] if end_text and end_text.strip() else None
    began = read(start_text, "start_text", keep)
    ended = None
    if end_text and not NOW.match(end_text.lower()):
        ended = read(end_text, "end_text", keep)
    row.start_text, row.end_text = start_text, end_text
    row.start_on = began.start if began else None
    row.end_on = _end_of(end_text, ended)
    if began and ended and row.start_on > row.end_on:
        row.start_on, row.end_on = ended.start, began.end
    row.dates_source = source if (start_text or end_text) else None


def may_overwrite(row, prefix: str) -> bool:
    return getattr(row, f"{prefix}_source") != MANUAL


def set_by_job(row, prefix: str, text: str | None, source: str) -> bool:
    """A job's date. Returns False, changing nothing, when a person set the date."""
    if not may_overwrite(row, prefix):
        return False
    set_point(row, prefix, text, source, keep=True)
    return True
