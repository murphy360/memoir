"""POST /api/dates/parse: how Memoir reads a date, before anything is saved."""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.dates.grammar import EXAMPLES, parse

router = APIRouter(prefix="/api/dates", tags=["dates"])


class DateText(BaseModel):
    text: str = Field(max_length=100)


class DateReading(BaseModel):
    ok: bool
    start: date | None = None
    end: date | None = None
    precision: str | None = None
    reading: str | None = Field(None, description='What Memoir understood: "July 1968"')
    message: str | None = None
    examples: list[str] = []


@router.post("/parse", response_model=DateReading)
def preview(body: DateText, _: User = Depends(require_role(Role.VIEWER))):
    """A read-only preview: it changes nothing, so a viewer may call it."""
    found = parse(body.text)
    if found is None:
        return DateReading(
            ok=False, message="Could not read this date.", examples=list(EXAMPLES)
        )
    return DateReading(
        ok=True,
        start=found.start,
        end=found.end,
        precision=found.precision,
        reading=found.reading,
    )
