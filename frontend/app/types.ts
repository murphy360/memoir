export type MemoryEntry = {
  id: number;
  transcript: string;
  event_description: string;
  estimated_date_text: string | null;
  date_precision: string | null;
  recorder_name: string | null;
  recorder_person_id: number | null;
  referenced_people: string[];
  referenced_locations: string[];
  emotional_tone: string;
  follow_up_question: string;
  audio_size_bytes: number | null;
  audio_url: string | null;
  date_recorded: string | null;
  created_at: string;
};

export type DirectoryEntry = {
  id: number;
  name: string;
  memory_count: number;
  aliases: string[];
};

export type Question = {
  id: number;
  text: string;
  source_memory_id: number | null;
  status: string;
  created_at: string;
};
