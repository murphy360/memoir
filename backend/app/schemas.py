from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transcript: str
    event_description: str
    estimated_date_text: Optional[str]
    date_precision: Optional[str]
    recorder_name: Optional[str]
    referenced_people: list[str] = Field(default_factory=list)
    referenced_locations: list[str] = Field(default_factory=list)
    emotional_tone: str
    follow_up_question: str
    audio_size_bytes: Optional[int]
    audio_url: Optional[str]
    created_at: datetime


class QuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    source_memory_id: Optional[int]
    status: str
    created_at: datetime


class AnswerQuestionRequest(BaseModel):
    answer_memory_id: Optional[int] = None
