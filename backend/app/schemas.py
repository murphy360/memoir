from datetime import datetime
from datetime import date
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
    recorder_person_id: Optional[int]
    referenced_people: list[str] = Field(default_factory=list)
    referenced_locations: list[str] = Field(default_factory=list)
    emotional_tone: str
    follow_up_question: str
    audio_size_bytes: Optional[int]
    audio_url: Optional[str]
    date_recorded: Optional[date]
    created_at: datetime


class QuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    source_memory_id: Optional[int]
    status: str
    created_at: datetime


class DirectoryEntryResponse(BaseModel):
    id: int
    name: str
    memory_count: int
    aliases: list[str] = Field(default_factory=list)


class CreateDirectoryEntryRequest(BaseModel):
    name: str


class UpdateDirectoryEntryRequest(BaseModel):
    name: str


class MergePersonRequest(BaseModel):
    into_person_id: int


class SplitPersonRequest(BaseModel):
    new_names: list[str]
    keep_alias: bool = True


class AddAliasRequest(BaseModel):
    alias: str


class UpdateMemoryRecorderRequest(BaseModel):
    person_id: Optional[int] = None
    recorder_name: Optional[str] = None


class AnswerQuestionRequest(BaseModel):
    answer_memory_id: Optional[int] = None
