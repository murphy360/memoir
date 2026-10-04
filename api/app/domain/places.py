"""Places: named locations that events, memories and photos can share."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Float, Index, String, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.core.db import Base, get_session
from app.core.errors import ApiError
from app.domain.common import ArchiveRow, clean, live, scoped, soft_delete
from app.domain.pagination import Page, PageParams, paginate


class Place(ArchiveRow, Base):
    __tablename__ = "places"
    __table_args__ = (
        Index(
            "uq_places_archive_name",
            "archive_id",
            func.lower("name"),
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)


class PlaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


class PlacePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


class PlaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    latitude: float | None
    longitude: float | None


def by_name(session: Session, user: User, name: str) -> Place | None:
    return session.scalars(
        scoped(Place, user).where(func.lower(Place.name) == name.strip().lower())
    ).first()


def _check_name(session: Session, user: User, name: str, me: int | None) -> str:
    name = clean(name, 200) or ""
    other = by_name(session, user, name)
    if not name or (other and other.id != me):
        raise ApiError(
            409, "name_taken", "There is already a place by that name.", "name"
        )
    return name


router = APIRouter(prefix="/api/places", tags=["places"])
reader = require_role(Role.VIEWER)
writer = require_role(Role.CONTRIBUTOR)


@router.get("", response_model=Page[PlaceOut])
def list_places(
    q: str | None = Query(None, max_length=200),
    page: PageParams = Depends(),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    stmt = scoped(Place, user)
    if q:
        stmt = stmt.where(func.lower(Place.name).like(f"%{q.strip().lower()}%"))
    rows, cursor = paginate(db, stmt, [func.lower(Place.name), Place.id], page)
    return Page(items=rows, next_cursor=cursor)


@router.post("", response_model=PlaceOut, status_code=201)
def create_place(
    body: PlaceIn, user: User = Depends(writer), db: Session = Depends(get_session)
):
    place = Place(
        archive_id=user.archive_id,
        name=_check_name(db, user, body.name, None),
        latitude=body.latitude,
        longitude=body.longitude,
    )
    db.add(place)
    db.commit()
    return place


@router.get("/{place_id}", response_model=PlaceOut)
def get_place(
    place_id: int, user: User = Depends(reader), db: Session = Depends(get_session)
):
    return live(db, Place, place_id, user, "place")


@router.patch("/{place_id}", response_model=PlaceOut)
def update_place(
    place_id: int,
    body: PlacePatch,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    place = live(db, Place, place_id, user, "place")
    sent = body.model_fields_set
    if "name" in sent and body.name:
        place.name = _check_name(db, user, body.name, place.id)
    for field in ("latitude", "longitude"):
        if field in sent:
            setattr(place, field, getattr(body, field))
    db.commit()
    return place


@router.delete("/{place_id}", status_code=204)
def remove_place(
    place_id: int, user: User = Depends(writer), db: Session = Depends(get_session)
) -> None:
    """Soft delete. Events, memories and photos that named it keep their own text."""
    soft_delete(live(db, Place, place_id, user, "place"))
    db.commit()
