import json
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    aliases: Mapped[list["PersonAlias"]] = relationship(back_populates="person", cascade="all, delete-orphan")
    tagged_faces: Mapped[list["AssetFace"]] = relationship(back_populates="person")


class PersonAlias(Base):
    """Alternative names / relationship terms that resolve to a Person.

    A single alias (e.g. 'parents') can map to *multiple* people by having
    one row per target person, so expand_person_names() can return both.
    """
    __tablename__ = "person_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    person: Mapped["Person"] = relationship(back_populates="aliases")


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MemoryPerson(Base):
    __tablename__ = "memory_people"
    __table_args__ = (UniqueConstraint("memory_id", "person_id", name="uq_memory_person"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    memory_id: Mapped[int] = mapped_column(ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default="mentioned")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    person: Mapped["Person"] = relationship()


class MemoryPlace(Base):
    __tablename__ = "memory_places"
    __table_args__ = (UniqueConstraint("memory_id", "place_id", name="uq_memory_place"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    memory_id: Mapped[int] = mapped_column(ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    place: Mapped["Place"] = relationship()


class MemoryEntry(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    transcript: Mapped[str] = mapped_column(Text)
    event_description: Mapped[str] = mapped_column(Text)
    estimated_date_text: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    estimated_date_sort: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_precision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    date_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    date_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    date_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    date_decade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_to_question_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_to_question_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorder_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    recorder_person_id: Mapped[Optional[int]] = mapped_column(ForeignKey("people.id"), nullable=True)
    people_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    locations_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emotional_tone: Mapped[str] = mapped_column(String(50), default="neutral")
    follow_up_question: Mapped[str] = mapped_column(Text)
    research_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    research_sources_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    research_queries_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    research_suggested_metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    audio_content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    audio_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    document_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    document_original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    document_content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    document_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    date_recorded: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    recorder_person: Mapped[Optional["Person"]] = relationship(foreign_keys=[recorder_person_id])
    people_links: Mapped[list["MemoryPerson"]] = relationship(cascade="all, delete-orphan")
    place_links: Mapped[list["MemoryPlace"]] = relationship(cascade="all, delete-orphan")

    @property
    def audio_url(self) -> Optional[str]:
        if not self.audio_filename:
            return None
        return f"/api/memories/{self.id}/audio"

    @property
    def document_url(self) -> Optional[str]:
        if not self.document_filename:
            return None
        return f"/api/memories/{self.id}/document"

    @property
    def referenced_people(self) -> list[str]:
        if self.people_links:
            return [link.person.name for link in self.people_links if link.person and link.person.name]
        return _deserialize_list(self.people_json)

    @property
    def referenced_locations(self) -> list[str]:
        if self.place_links:
            return [link.place.name for link in self.place_links if link.place and link.place.name]
        return _deserialize_list(self.locations_json)

    @property
    def research_sources(self) -> list[dict[str, str]]:
        return _deserialize_object_list(self.research_sources_json)

    @property
    def research_queries(self) -> list[str]:
        return _deserialize_list(self.research_queries_json)

    @property
    def research_suggested_metadata(self) -> Optional[dict[str, Any]]:
        if not self.research_suggested_metadata_json:
            return None
        try:
            value = json.loads(self.research_suggested_metadata_json)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


class LifePeriod(Base):
    __tablename__ = "life_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    slug: Mapped[Optional[str]] = mapped_column(String(180), nullable=True, unique=True, index=True)
    start_date_text: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    end_date_text: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    start_sort: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_sort: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    events: Mapped[list["LifeEvent"]] = relationship(back_populates="period", cascade="all, delete-orphan")
    assets: Mapped[list["Asset"]] = relationship(back_populates="period", cascade="all, delete-orphan")


class LifeEvent(Base):
    __tablename__ = "life_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    period_id: Mapped[Optional[int]] = mapped_column(ForeignKey("life_periods.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    research_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    research_sources_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    research_queries_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    research_suggested_edit_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_date_text: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    event_date_sort: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    date_precision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    date_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    date_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    date_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    date_decade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    legacy_memory_id: Mapped[Optional[int]] = mapped_column(ForeignKey("memories.id", ondelete="SET NULL"), nullable=True, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    period: Mapped[Optional["LifePeriod"]] = relationship(back_populates="events")
    linked_assets: Mapped[list["EventAsset"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    legacy_memory: Mapped[Optional["MemoryEntry"]] = relationship(foreign_keys=[legacy_memory_id])

    @property
    def research_sources(self) -> list[dict[str, str]]:
        return _deserialize_object_list(self.research_sources_json)

    @property
    def research_queries(self) -> list[str]:
        return _deserialize_list(self.research_queries_json)

    @property
    def research_suggested_edit(self) -> Optional[dict[str, Any]]:
        if not self.research_suggested_edit_json:
            return None
        try:
            value = json.loads(self.research_suggested_edit_json)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


class EventAsset(Base):
    __tablename__ = "event_assets"
    __table_args__ = (UniqueConstraint("event_id", "asset_id", name="uq_event_asset"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("life_events.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(30), default="evidence")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    event: Mapped["LifeEvent"] = relationship(back_populates="linked_assets")
    asset: Mapped["Asset"] = relationship(back_populates="event_links")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    period_id: Mapped[Optional[int]] = mapped_column(ForeignKey("life_periods.id", ondelete="SET NULL"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="document", index=True)
    title: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    storage_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fingerprint_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    text_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    captured_at_text: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gps_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gps_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    camera_make: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    camera_model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    lens_model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    orientation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    exif_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    legacy_memory_id: Mapped[Optional[int]] = mapped_column(ForeignKey("memories.id", ondelete="SET NULL"), nullable=True, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    period: Mapped[Optional["LifePeriod"]] = relationship(back_populates="assets")
    event_links: Mapped[list["EventAsset"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    faces: Mapped[list["AssetFace"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    legacy_memory: Mapped[Optional["MemoryEntry"]] = relationship(foreign_keys=[legacy_memory_id])

    @property
    def download_url(self) -> str:
        return f"/api/assets/{self.id}/download"


class AssetFace(Base):
    __tablename__ = "asset_faces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    # Bounding box values are normalized to [0, 1] against image width/height.
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_w: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_h: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # person_id stays null until a user manually assigns the detected face.
    person_id: Mapped[Optional[int]] = mapped_column(ForeignKey("people.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    asset: Mapped["Asset"] = relationship(back_populates="faces")
    person: Mapped[Optional["Person"]] = relationship(back_populates="tagged_faces")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    text: Mapped[str] = mapped_column(Text)
    source_memory_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    answer_memory_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def _deserialize_list(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(item) for item in value if isinstance(item, str)]
    except json.JSONDecodeError:
        return []
    return []


def _deserialize_object_list(raw: Optional[str]) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if not isinstance(value, list):
            return []
    except json.JSONDecodeError:
        return []

    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized: dict[str, Any] = {}
        for key, candidate in item.items():
            if isinstance(key, str) and isinstance(candidate, str):
                normalized[key] = candidate
        if normalized:
            result.append(normalized)
    return result
