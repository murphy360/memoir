export type MemoryEntry = {
  id: number;
  transcript: string;
  event_description: string;
  estimated_date_text: string | null;
  date_precision: string | null;
  recorder_name: string | null;
  referenced_people: string[];
  referenced_locations: string[];
  emotional_tone: string;
  follow_up_question: string;
  audio_size_bytes: number | null;
  audio_url: string | null;
  created_at: string;
};

export type Question = {
  id: number;
  text: string;
  source_memory_id: number | null;
  status: string;
  created_at: string;
};
