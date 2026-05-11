export type ResearchSource = {
  title: string;
  url: string;
};

export type ResearchDateSuggestion = {
  estimated_date_text: string;
  date_precision: string;
  date_year: number | null;
  date_month: number | null;
  date_day: number | null;
  date_decade: number | null;
  reasoning: string;
};

export type EventEditSuggestion = {
  title: string | null;
  event_date_text: string | null;
  description: string | null;
  reasoning: string;
};

export type MemoryEntry = {
  id: number;
  transcript: string;
  event_description: string;
  estimated_date_text: string | null;
  date_precision: string | null;
  response_to_question_id: number | null;
  response_to_question_text: string | null;
  recorder_name: string | null;
  recorder_person_id: number | null;
  referenced_people: string[];
  referenced_locations: string[];
  emotional_tone: string;
  follow_up_question: string;
  research_summary: string | null;
  research_queries: string[];
  research_sources: ResearchSource[];
  research_suggested_metadata: ResearchDateSuggestion | null;
  audio_size_bytes: number | null;
  audio_url: string | null;
  document_filename: string | null;
  document_size_bytes: number | null;
  document_url: string | null;
  date_recorded: string | null;
  created_at: string;
};

export type DirectoryEntry = {
  id: number;
  name: string;
  memory_count: number;
  photo_count: number;
  aliases: string[];
  avatar_download_url: string | null;
  /** Non-null when this person is linked to exactly one CompreFace subject. */
  compreface_subject_id: string | null;
  /** Direct CompreFace API URL for the linked subject when NEXT_PUBLIC_API_BASE_URL can reach it. */
  compreface_subject_url: string | null;
};

export type Question = {
  id: number;
  text: string;
  source_memory_id: number | null;
  status: string;
  created_at: string;
};

export type AppSettings = {
  main_character_name: string | null;
};

export type LifePeriod = {
  id: number;
  title: string;
  slug: string | null;
  start_date_text: string | null;
  end_date_text: string | null;
  summary: string | null;
  event_count: number;
  epic_count: number;
  asset_count: number;
  created_at: string;
  updated_at: string;
};

/** Top-level parallel life track that groups multiple periods. */
export type LifeThread = {
  id: number;
  title: string;
  slug: string | null;
  summary: string | null;
  event_count: number;
  epic_count: number;
  created_at: string;
  updated_at: string;
};

/** Mid-level event grouping inside a period; used for arcs like deployment or vacation. */
export type LifeEpic = {
  id: number;
  period_id: number;
  thread_id: number | null;
  title: string;
  description: string | null;
  weight: number;
  start_date_text: string | null;
  end_date_text: string | null;
  event_count: number;
  created_at: string;
  updated_at: string;
};

export type LifePeriodAnalysis = {
  period_id: number;
  event_count: number;
  asset_count: number;
  coverage_ok: boolean;
  coverage_reasoning: string;
  current_title: string;
  recommended_titles: string[];
  title_reasoning: string;
  current_start_date_text: string | null;
  current_end_date_text: string | null;
  recommended_start_date_text: string | null;
  recommended_end_date_text: string | null;
  generated_summary: string | null;
  summary_reasoning: string;
  queued_event_count: number;
  analyzed_event_count: number;
  skipped_event_count: number;
  failed_event_count: number;
  photo_assets_analyzed: number;
  memories_researched: number;
};

export type LifeEvent = {
  id: number;
  period_id: number | null;
  epic_id: number | null;
  thread_id: number | null;
  title: string;
  description: string | null;
  weight: number;
  summary: string | null;
  research_summary: string | null;
  research_queries: string[];
  research_sources: ResearchSource[];
  research_suggested_edit: EventEditSuggestion | null;
  event_date_text: string | null;
  location: string | null;
  date_precision: string | null;
  date_year: number | null;
  date_month: number | null;
  date_day: number | null;
  date_decade: number | null;
  legacy_memory_id: number | null;
  linked_memory_ids: number[];
  legacy_audio_url: string | null;
  legacy_audio_size_bytes: number | null;
  linked_asset_count: number;
  analysis_status: string | null;
  analysis_last_analyzed_at: string | null;
  analysis_last_error: string | null;
  created_at: string;
  updated_at: string;
};

export type AssetEntry = {
  id: number;
  period_id: number | null;
  kind: string;
  title: string | null;
  gemini_suggested_title: string | null;
  legacy_memory_id: number | null;
  original_filename: string | null;
  content_type: string | null;
  size_bytes: number | null;
  captured_at: string | null;
  captured_at_text: string | null;
  gps_latitude: number | null;
  gps_longitude: number | null;
  // Place text read directly from EXIF tags when present.
  exif_place_name: string | null;
  // Human-readable locality from reverse geocoding EXIF GPS coordinates.
  reverse_geocode_location_name: string | null;
  // Gemini best-effort place inference from image content + metadata.
  analyzed_place_name: string | null;
  location_name: string | null;
  camera_make: string | null;
  camera_model: string | null;
  lens_model: string | null;
  orientation: number | null;
  image_width: number | null;
  image_height: number | null;
  playback_url: string | null;
  text_excerpt: string | null;
  notes: string | null;
  download_url: string;
  linked_event_ids: number[];
  created_at: string;
};

/**
 * One detected face region from a photo asset linked to an event.
 * person_id/person_name can be set automatically when CompreFace subject
 * matches a known person (or alias) with sufficient confidence.
 * compreface_* fields capture raw recognition metadata when available.
 */
export type EventFaceEntry = {
  id: number;
  asset_id: number;
  asset_title: string | null;
  asset_download_url: string;
  bbox_x: number;
  bbox_y: number;
  bbox_w: number;
  bbox_h: number;
  confidence: number | null;
  compreface_subject: string | null;
  compreface_similarity: number | null;
  compreface_gender: string | null;
  compreface_age_low: number | null;
  compreface_age_high: number | null;
  compreface_raw: Record<string, unknown> | null;
  person_id: number | null;
  person_name: string | null;
};
