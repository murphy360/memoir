import json
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
    recorder_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    people_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    locations_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emotional_tone: Mapped[str] = mapped_column(String(50), default="neutral")
    follow_up_question: Mapped[str] = mapped_column(Text)
    audio_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    audio_content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    audio_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def audio_url(self) -> Optional[str]:
        if not self.audio_filename:
            return None
        return f"/api/memories/{self.id}/audio"

    @property
    def referenced_people(self) -> list[str]:
        return _deserialize_list(self.people_json)

    @property
    def referenced_locations(self) -> list[str]:
        return _deserialize_list(self.locations_json)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    text: Mapped[str] = mapped_column(Text)
    source_memory_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    answer_memory_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
