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


class EventEditSuggestionResponse(BaseModel):
    title: Optional[str] = None
    event_date_text: Optional[str] = None
    description: Optional[str] = None
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
    apply_dates: bool = Field(default=False, description="Apply recommended period start/end dates to the period record.")
    apply_title: bool = Field(default=False, description="Apply the top recommended period title.")
    apply_title_text: Optional[str] = Field(default=None, description="Apply this exact title text to the period when provided.")
    regenerate_summary: bool = Field(default=False, description="Force writing a refreshed period summary back to the period.")
    reanalyze_events: bool = Field(default=False, description="Force re-running event asset/memory analysis even when inputs are unchanged.")


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
    queued_event_count: int = Field(default=0, description="How many period events were queued for analysis in this run.")
    analyzed_event_count: int = Field(default=0, description="How many events were fully analyzed in this run.")
    skipped_event_count: int = Field(default=0, description="How many events were skipped because their analysis inputs were unchanged.")
    failed_event_count: int = Field(default=0, description="How many event analysis attempts failed.")
    photo_assets_analyzed: int = Field(default=0, description="How many photo assets were processed while analyzing queued events.")
    memories_researched: int = Field(default=0, description="How many linked memories were deeply researched while analyzing queued events.")


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
    research_suggested_edit: Optional[EventEditSuggestionResponse] = None
    location: Optional[str]
    event_date_text: Optional[str]
    date_precision: Optional[str]
    date_year: Optional[int]
    date_month: Optional[int]
    date_day: Optional[int]
    date_decade: Optional[int]
    legacy_memory_id: Optional[int]
    linked_memory_ids: list[int] = Field(default_factory=list)
    legacy_audio_url: Optional[str]
    legacy_audio_size_bytes: Optional[int]
    linked_asset_count: int = 0
    analysis_status: Optional[str] = Field(default=None, description="Latest event analysis state such as running, completed, skipped, or failed.")
    analysis_last_analyzed_at: Optional[datetime] = Field(default=None, description="UTC timestamp of the most recent successful event analysis.")
    analysis_last_error: Optional[str] = Field(default=None, description="Truncated error from the most recent failed event analysis attempt.")
    created_at: datetime
    updated_at: datetime


class CreateLifeEventRequest(BaseModel):
    title: str
    period_id: Optional[int] = None
    description: Optional[str] = None
    location: Optional[str] = None
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
    description: Optional[str] = None
    location: Optional[str] = None
    event_date_text: Optional[str] = None
    period_id: Optional[int] = None


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


class EventFaceResponse(BaseModel):
    id: int = Field(description="Face detection row id.")
    asset_id: int = Field(description="Photo asset id that contains the detected face.")
    asset_title: Optional[str] = Field(default=None, description="Best display title of the source photo asset.")
    asset_download_url: str = Field(description="Download URL for the source photo.")
    bbox_x: float = Field(description="Left coordinate normalized to [0, 1] of image width.")
    bbox_y: float = Field(description="Top coordinate normalized to [0, 1] of image height.")
    bbox_w: float = Field(description="Box width normalized to [0, 1] of image width.")
    bbox_h: float = Field(description="Box height normalized to [0, 1] of image height.")
    confidence: Optional[float] = Field(default=None, description="Detector confidence when available.")
    person_id: Optional[int] = Field(default=None, description="Assigned person id for this face, if manually linked.")
    person_name: Optional[str] = Field(default=None, description="Assigned person display name, if manually linked.")


class AssignFacePersonRequest(BaseModel):
    person_id: Optional[int] = Field(default=None, description="Person id to assign, or null to clear assignment.")


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
    avatar_download_url: Optional[str] = Field(default=None, description="Photo URL for this person card avatar, when available.")


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
