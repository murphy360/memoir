"""Assets: the files a family keeps (photos, documents, recordings) and the events they
show. An asset linked to no live event is in the inbox.

The file itself is a blob (`app/blobs`). Uploading, photo metadata and analysis come
with their own tickets; this module keeps the record and its links.
"""

from datetime import date
from enum import StrEnum

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    CHAR,
    Date,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.accounts.deps import require_role
from app.accounts.models import Role, User
from app.blobs.models import Blob
from app.core.db import Base, get_session
from app.core.errors import ApiError
from app.dates.store import MANUAL, set_point
from app.domain.common import LAST_DAY, ArchiveRow, clean, live, scoped, soft_delete
from app.domain.events import Event
from app.domain.pagination import Page, PageParams, paginate
from app.domain.places import Place


class Kind(StrEnum):
    PHOTO = "photo"
    DOCUMENT = "document"
    AUDIO = "audio"


class Relation(StrEnum):
    EVIDENCE = "evidence"
    RECORDING = "recording"


class Asset(ArchiveRow, Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str | None] = mapped_column(String(180))
    notes: Mapped[str | None] = mapped_column(Text)
    # The file. Its hash doubles as the duplicate check: the same bytes are the same
    # blob.
    blob_sha256: Mapped[str] = mapped_column(
        CHAR(64), ForeignKey("blobs.sha256", ondelete="RESTRICT"), index=True
    )
    original_filename: Mapped[str | None] = mapped_column(String(255))
    excerpt: Mapped[str | None] = mapped_column(Text)
    capture_text: Mapped[str | None] = mapped_column(String(100))
    capture_start: Mapped[date | None] = mapped_column(Date)
    capture_end: Mapped[date | None] = mapped_column(Date)
    capture_precision: Mapped[str | None] = mapped_column(String(16))
    capture_source: Mapped[str | None] = mapped_column(String(16))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    exif_place_name: Mapped[str | None] = mapped_column(String(200))
    geocoded_place_name: Mapped[str | None] = mapped_column(String(200))
    analyzed_place_name: Mapped[str | None] = mapped_column(String(200))
    place_id: Mapped[int | None] = mapped_column(
        ForeignKey("places.id", ondelete="SET NULL"), index=True
    )


class EventAsset(Base):
    __tablename__ = "event_assets"
    __table_args__ = (UniqueConstraint("event_id", "asset_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), index=True
    )
    relation: Mapped[str] = mapped_column(String(16), default=Relation.EVIDENCE)


class AssetIn(BaseModel):
    blob_sha256: str = Field(min_length=64, max_length=64)
    kind: Kind
    title: str | None = Field(None, max_length=180)
    notes: str | None = None
    original_filename: str | None = Field(None, max_length=255)
    capture_text: str | None = Field(None, max_length=100)
    place_id: int | None = None
    keep_text_only: bool = Field(
        False, description="Save a date Memoir cannot read, as text only"
    )


class AssetPatch(BaseModel):
    title: str | None = Field(None, max_length=180)
    notes: str | None = None
    capture_text: str | None = Field(None, max_length=100)
    place_id: int | None = None
    keep_text_only: bool = Field(
        False, description="Save a date Memoir cannot read, as text only"
    )


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: Kind
    title: str | None
    notes: str | None
    blob_sha256: str
    original_filename: str | None
    excerpt: str | None
    capture_text: str | None
    capture_start: date | None
    capture_end: date | None
    latitude: float | None
    longitude: float | None
    exif_place_name: str | None
    geocoded_place_name: str | None
    analyzed_place_name: str | None
    place_id: int | None
    event_ids: list[int] = []


class LinkIn(BaseModel):
    relation: Relation = Relation.EVIDENCE


def out(session: Session, assets: list[Asset]) -> list[AssetOut]:
    ids = [a.id for a in assets]
    links: dict[int, list[int]] = {i: [] for i in ids}
    rows = session.execute(
        select(EventAsset.asset_id, EventAsset.event_id)
        .join(Event, Event.id == EventAsset.event_id)
        .where(EventAsset.asset_id.in_(ids), Event.deleted_at.is_(None))
        .order_by(EventAsset.id)
    )
    for asset_id, event_id in rows:
        links[asset_id].append(event_id)
    return [
        AssetOut.model_validate(a).model_copy(update={"event_ids": links[a.id]})
        for a in assets
    ]


def link(session: Session, event: Event, asset: Asset, relation: Relation) -> None:
    row = session.scalars(
        select(EventAsset).where(
            EventAsset.event_id == event.id, EventAsset.asset_id == asset.id
        )
    ).first() or EventAsset(event_id=event.id, asset_id=asset.id)
    row.relation = relation
    session.add(row)
    session.commit()


router = APIRouter(tags=["assets"])
reader = require_role(Role.VIEWER)
writer = require_role(Role.CONTRIBUTOR)


@router.get("/api/assets", response_model=Page[AssetOut])
def list_assets(
    event_id: int | None = Query(None),
    inbox: bool = Query(False, description="Only assets linked to no live event"),
    sha256: str | None = Query(None, description="Find a file already kept"),
    page: PageParams = Depends(),
    user: User = Depends(reader),
    db: Session = Depends(get_session),
):
    stmt = scoped(Asset, user)
    linked = (
        select(EventAsset.asset_id)
        .join(Event, Event.id == EventAsset.event_id)
        .where(Event.deleted_at.is_(None))
    )
    if event_id:
        stmt = stmt.where(Asset.id.in_(linked.where(EventAsset.event_id == event_id)))
    if inbox:
        stmt = stmt.where(Asset.id.not_in(linked))
    if sha256:
        stmt = stmt.where(Asset.blob_sha256 == sha256)
    keys = [func.coalesce(Asset.capture_start, LAST_DAY), Asset.id]
    rows, cursor = paginate(db, stmt, keys, page)
    return Page(items=out(db, rows), next_cursor=cursor)


@router.post("/api/assets", response_model=AssetOut, status_code=201)
def create_asset(
    body: AssetIn, user: User = Depends(writer), db: Session = Depends(get_session)
):
    if db.get(Blob, body.blob_sha256) is None:
        raise ApiError(
            422, "no_such_blob", "That file has not been uploaded.", "blob_sha256"
        )
    if body.place_id:
        live(db, Place, body.place_id, user, "place")
    asset = Asset(
        archive_id=user.archive_id,
        kind=body.kind,
        title=clean(body.title, 180),
        notes=clean(body.notes, 20_000),
        blob_sha256=body.blob_sha256,
        original_filename=clean(body.original_filename, 255),
        place_id=body.place_id,
    )
    set_point(asset, "capture", body.capture_text, MANUAL, body.keep_text_only)
    db.add(asset)
    db.commit()
    return out(db, [asset])[0]


@router.get("/api/assets/{asset_id}", response_model=AssetOut)
def get_asset(
    asset_id: int, user: User = Depends(reader), db: Session = Depends(get_session)
):
    return out(db, [live(db, Asset, asset_id, user, "asset")])[0]


@router.patch("/api/assets/{asset_id}", response_model=AssetOut)
def update_asset(
    asset_id: int,
    body: AssetPatch,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    asset = live(db, Asset, asset_id, user, "asset")
    sent = body.model_fields_set
    for field, limit in (("title", 180), ("notes", 20_000)):
        if field in sent:
            setattr(asset, field, clean(getattr(body, field), limit))
    if "capture_text" in sent:
        set_point(asset, "capture", body.capture_text, MANUAL, body.keep_text_only)
    if "place_id" in sent:
        if body.place_id:
            live(db, Place, body.place_id, user, "place")
        asset.place_id = body.place_id
    db.commit()
    return out(db, [asset])[0]


@router.delete("/api/assets/{asset_id}", status_code=204)
def remove_asset(
    asset_id: int, user: User = Depends(writer), db: Session = Depends(get_session)
) -> None:
    """Soft delete. The file stays until the asset is purged and nothing
    else uses it.
    """
    soft_delete(live(db, Asset, asset_id, user, "asset"))
    db.commit()


@router.put("/api/events/{event_id}/assets/{asset_id}", response_model=AssetOut)
def link_asset(
    event_id: int,
    asset_id: int,
    body: LinkIn,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    asset = live(db, Asset, asset_id, user, "asset")
    link(db, live(db, Event, event_id, user, "event"), asset, body.relation)
    return out(db, [asset])[0]


@router.delete("/api/events/{event_id}/assets/{asset_id}", response_model=AssetOut)
def unlink_asset(
    event_id: int,
    asset_id: int,
    user: User = Depends(writer),
    db: Session = Depends(get_session),
):
    asset = live(db, Asset, asset_id, user, "asset")
    live(db, Event, event_id, user, "event")
    row = db.scalars(
        select(EventAsset).where(
            EventAsset.event_id == event_id, EventAsset.asset_id == asset.id
        )
    ).first()
    if row is not None:
        db.delete(row)
        db.commit()
    return out(db, [asset])[0]
