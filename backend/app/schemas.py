from datetime import datetime
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ResearchSourceResponse(BaseModel):
    title: str
    url: str


class ResearchDateSuggestion(BaseModel):
    estimated_date_text: str
    date_precision: str
    date_year: Optional[int]
    date_month: Optional[int]
    date_day: Optional[int]
    date_decade: Optional[int]
    reasoning: str


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transcript: str
    event_description: str
    estimated_date_text: Optional[str]
    date_precision: Optional[str]
    response_to_question_id: Optional[int]
    response_to_question_text: Optional[str]
    recorder_name: Optional[str]
    recorder_person_id: Optional[int]
    referenced_people: list[str] = Field(default_factory=list)
    referenced_locations: list[str] = Field(default_factory=list)
    emotional_tone: str
    follow_up_question: str
    research_summary: Optional[str]
    research_queries: list[str] = Field(default_factory=list)
    research_sources: list[ResearchSourceResponse] = Field(default_factory=list)
    research_suggested_metadata: Optional[ResearchDateSuggestion] = None
    audio_size_bytes: Optional[int]
    audio_url: Optional[str]
    document_filename: Optional[str]
    document_size_bytes: Optional[int]
    document_url: Optional[str]
    date_recorded: Optional[date]
    created_at: datetime


class LifePeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: Optional[str]
    start_date_text: Optional[str]
    end_date_text: Optional[str]
    summary: Optional[str]
    event_count: int = 0
    asset_count: int = 0
    created_at: datetime
    updated_at: datetime


class CreateLifePeriodRequest(BaseModel):
    title: str
    start_date_text: Optional[str] = None
    end_date_text: Optional[str] = None
    summary: Optional[str] = None


class AnalyzeLifePeriodRequest(BaseModel):
    apply_dates: bool = False
    apply_title: bool = False
    apply_title_text: Optional[str] = None
    regenerate_summary: bool = False


class UpdateLifePeriodRequest(BaseModel):
    title: Optional[str] = None
    start_date_text: Optional[str] = None
    end_date_text: Optional[str] = None


class MergePeriodsRequest(BaseModel):
    into_period_id: int  # events/assets from the deleted period move here


class LifePeriodAnalysisResponse(BaseModel):
    period_id: int
    event_count: int
    asset_count: int
    coverage_ok: bool
    coverage_reasoning: str
    current_title: str
    recommended_titles: list[str] = []
    title_reasoning: str
    current_start_date_text: Optional[str] = None
    current_end_date_text: Optional[str] = None
    recommended_start_date_text: Optional[str] = None
    recommended_end_date_text: Optional[str] = None
    generated_summary: Optional[str] = None
    summary_reasoning: str


class LifeEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_id: Optional[int]
    title: str
    description: Optional[str]
    summary: Optional[str]
    research_summary: Optional[str]
    research_queries: list[str] = Field(default_factory=list)
    research_sources: list[ResearchSourceResponse] = Field(default_factory=list)
    event_date_text: Optional[str]
    date_precision: Optional[str]
    date_year: Optional[int]
    date_month: Optional[int]
    date_day: Optional[int]
    date_decade: Optional[int]
    legacy_memory_id: Optional[int]
    legacy_audio_url: Optional[str]
    legacy_audio_size_bytes: Optional[int]
    linked_asset_count: int = 0
    created_at: datetime
    updated_at: datetime


class CreateLifeEventRequest(BaseModel):
    title: str
    period_id: Optional[int] = None
    description: Optional[str] = None
    event_date_text: Optional[str] = None
    date_precision: Optional[str] = None
    date_year: Optional[int] = None
    date_month: Optional[int] = None
    date_day: Optional[int] = None
    date_decade: Optional[int] = None


class MergeLifeEventRequest(BaseModel):
    into_event_id: int


class UpdateLifeEventRequest(BaseModel):
    title: Optional[str] = None


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_id: Optional[int]
    kind: str
    title: Optional[str]
    legacy_memory_id: Optional[int]
    original_filename: Optional[str]
    content_type: Optional[str]
    size_bytes: Optional[int]
    captured_at: Optional[datetime]
    captured_at_text: Optional[str]
    gps_latitude: Optional[float]
    gps_longitude: Optional[float]
    camera_make: Optional[str]
    camera_model: Optional[str]
    lens_model: Optional[str]
    orientation: Optional[int]
    image_width: Optional[int]
    image_height: Optional[int]
    playback_url: Optional[str]
    text_excerpt: Optional[str]
    notes: Optional[str]
    download_url: str
    linked_event_ids: list[int] = Field(default_factory=list)
    created_at: datetime


class LinkAssetToEventRequest(BaseModel):
    relation_type: Optional[str] = "evidence"


class UpdateAssetRequest(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None


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


class UpdateMemoryRequest(BaseModel):
    event_description: Optional[str] = None


class AnswerQuestionRequest(BaseModel):
    answer_memory_id: Optional[int] = None


class SettingsResponse(BaseModel):
    main_character_name: Optional[str] = None


class UpdateSettingRequest(BaseModel):
    value: Optional[str] = None
