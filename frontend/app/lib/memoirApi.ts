import {
  AppSettings,
  AssetEntry,
  DirectoryEntry,
  EventFaceEntry,
  LifeEvent,
  LifePeriod,
  LifePeriodAnalysis,
  MemoryEntry,
  Question,
} from "../types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";

function toAbsoluteApiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE}${path}`;
}

async function expectOk(response: Response, message: string): Promise<void> {
  if (!response.ok) {
    let detail = "";
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await response.json().catch(() => null);
      if (data && typeof data.detail === "string") {
        detail = data.detail;
      } else if (data) {
        detail = JSON.stringify(data);
      }
    } else {
      detail = await response.text().catch(() => "");
    }
    throw new Error(detail ? `${message}: ${detail}` : message);
  }
}

export function resolveApiUrl(path: string): string {
  return toAbsoluteApiUrl(path);
}

export type TimelineBundle = {
  memories: MemoryEntry[];
  questions?: Question[];
  people?: DirectoryEntry[];
  places?: DirectoryEntry[];
  settings?: AppSettings;
  periods?: LifePeriod[];
  events?: LifeEvent[];
  unlinkedAssets?: AssetEntry[];
};

export async function fetchTimelineBundle(): Promise<TimelineBundle> {
  const [
    memoriesRes,
    questionsRes,
    peopleRes,
    placesRes,
    settingsRes,
    periodsRes,
    eventsRes,
    unlinkedAssetsRes,
  ] = await Promise.all([
    fetch(toAbsoluteApiUrl("/api/memories"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/questions"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/people"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/places"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/settings"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/periods"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/events"), { cache: "no-store" }),
    fetch(toAbsoluteApiUrl("/api/assets/unlinked"), { cache: "no-store" }),
  ]);

  await expectOk(memoriesRes, "Failed to load timeline");

  const bundle: TimelineBundle = {
    memories: await memoriesRes.json(),
  };

  if (questionsRes.ok) {
    bundle.questions = await questionsRes.json();
  }
  if (peopleRes.ok) {
    bundle.people = await peopleRes.json();
  }
  if (placesRes.ok) {
    bundle.places = await placesRes.json();
  }
  if (settingsRes.ok) {
    bundle.settings = await settingsRes.json();
  }
  if (periodsRes.ok) {
    bundle.periods = await periodsRes.json();
  }
  if (eventsRes.ok) {
    bundle.events = await eventsRes.json();
  }
  if (unlinkedAssetsRes.ok) {
    bundle.unlinkedAssets = await unlinkedAssetsRes.json();
  }

  return bundle;
}

export async function fetchEventAssets(eventId: number): Promise<AssetEntry[]> {
  const response = await fetch(toAbsoluteApiUrl(`/api/events/${eventId}/assets`), { cache: "no-store" });
  await expectOk(response, "Failed to load event assets");
  return response.json();
}

/** Load detected faces for one event from GET /api/events/{event_id}/faces. */
export async function fetchEventFaces(eventId: number): Promise<EventFaceEntry[]> {
  const response = await fetch(toAbsoluteApiUrl(`/api/events/${eventId}/faces`), { cache: "no-store" });
  await expectOk(response, "Failed to load event faces");
  return response.json();
}

/** Assign or clear person link for a detected face via POST /api/faces/{face_id}/assign-person. */
export async function assignFacePerson(faceId: number, personId: number | null): Promise<EventFaceEntry> {
  const response = await fetch(toAbsoluteApiUrl(`/api/faces/${faceId}/assign-person`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ person_id: personId }),
  });

  await expectOk(response, "Failed to assign face");
  return response.json();
}

/** Permanently delete a detected face record via DELETE /api/faces/{face_id}. */
export async function deleteFace(faceId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/faces/${faceId}`), { method: "DELETE" });
  await expectOk(response, "Failed to delete face");
}

export async function createPeriod(payload: {
  title: string;
  start_date_text: string | null;
  end_date_text: string | null;
  summary: string | null;
}): Promise<LifePeriod> {
  const response = await fetch(toAbsoluteApiUrl("/api/periods"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await expectOk(response, "Create period failed");
  return response.json();
}

export async function createEvent(payload: {
  title: string;
  period_id: number | null;
  description: string | null;
  location: string | null;
  event_date_text: string | null;
}): Promise<LifeEvent> {
  const response = await fetch(toAbsoluteApiUrl("/api/events"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await expectOk(response, "Create event failed");
  return response.json();
}

export async function analyzeLifePeriod(
  periodId: number,
  payload: { apply_dates: boolean; apply_title: boolean; regenerate_summary: boolean; reanalyze_events?: boolean },
): Promise<LifePeriodAnalysis> {
  const response = await fetch(toAbsoluteApiUrl(`/api/periods/${periodId}/analyze`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await expectOk(response, "Analyze period failed");
  return response.json();
}

export async function renameEventTitle(eventId: number, title: string): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/events/${eventId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  await expectOk(response, "Failed to rename event");
}

export async function updateEventById(
  eventId: number,
  payload: { title?: string; event_date_text?: string | null; description?: string | null; location?: string | null; period_id?: number | null },
): Promise<LifeEvent> {
  const response = await fetch(toAbsoluteApiUrl(`/api/events/${eventId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await expectOk(response, "Failed to update event");
  return response.json();
}

export async function renamePeriodTitle(periodId: number, title: string): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/periods/${periodId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  await expectOk(response, "Failed to rename period");
}

export async function updatePeriodDates(
  periodId: number,
  startDateText: string | null,
  endDateText: string | null,
): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/periods/${periodId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ start_date_text: startDateText, end_date_text: endDateText }),
  });
  await expectOk(response, "Failed to update period dates");
}

export async function deletePeriodById(periodId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/periods/${periodId}`), { method: "DELETE" });
  await expectOk(response, "Failed to delete period");
}

export async function mergePeriodInto(fromPeriodId: number, intoPeriodId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/periods/${fromPeriodId}/merge`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ into_period_id: intoPeriodId }),
  });
  await expectOk(response, "Failed to merge period");
}

export async function uploadAsset(formData: FormData): Promise<AssetEntry> {
  const response = await fetch(toAbsoluteApiUrl("/api/assets"), {
    method: "POST",
    body: formData,
  });
  await expectOk(response, "Upload asset failed");
  return response.json();
}

/** Process event photos via POST /api/assets/photos/process-events, optionally including already-processed assets for re-runs. */
export async function processEventPhotoAssets(
  eventId: number,
  includeProcessed = false,
): Promise<{ events_processed: number; photos_processed: number; processed_asset_ids: number[] }> {
  const response = await fetch(toAbsoluteApiUrl("/api/assets/photos/process-events"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id: eventId, include_processed: includeProcessed }),
  });
  await expectOk(response, "Process event photos failed");
  return response.json();
}

export async function deleteAsset(assetId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/assets/${assetId}`), {
    method: "DELETE",
  });
  await expectOk(response, "Delete asset failed");
}

export async function updateAssetNotes(assetId: number, notes: string | null): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/assets/${assetId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
  await expectOk(response, "Update asset notes failed");
}

export async function updateAssetTitle(assetId: number, title: string | null): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/assets/${assetId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  await expectOk(response, "Update asset title failed");
}

export async function linkAssetToEvent(
  assetId: number,
  eventId: number,
  relationType: string,
): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/assets/${assetId}/link-event/${eventId}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ relation_type: relationType }),
  });
  await expectOk(response, "Link asset failed");
}

export async function deleteEventById(eventId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/events/${eventId}`), {
    method: "DELETE",
  });
  await expectOk(response, "Delete event failed");
}

export async function mergeEventInto(sourceId: number, targetId: number): Promise<LifeEvent> {
  const response = await fetch(toAbsoluteApiUrl(`/api/events/${sourceId}/merge`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ into_event_id: targetId }),
  });
  await expectOk(response, "Merge event failed");
  return response.json();
}

export async function summarizeEventById(eventId: number): Promise<LifeEvent> {
  const response = await fetch(toAbsoluteApiUrl(`/api/events/${eventId}/summarize`), {
    method: "POST",
  });
  await expectOk(response, "Event summary failed");
  return response.json();
}

export async function researchEventById(eventId: number): Promise<LifeEvent> {
  const response = await fetch(toAbsoluteApiUrl(`/api/events/${eventId}/research`), {
    method: "POST",
  });
  await expectOk(response, "Event research failed");
  return response.json();
}

export async function applyEventResearchSuggestionById(eventId: number): Promise<LifeEvent> {
  const response = await fetch(toAbsoluteApiUrl(`/api/events/${eventId}/apply-research-suggestion`), {
    method: "POST",
  });
  await expectOk(response, "Apply event suggestion failed");
  return response.json();
}

export async function dismissEventResearchSuggestionById(eventId: number): Promise<LifeEvent> {
  const response = await fetch(toAbsoluteApiUrl(`/api/events/${eventId}/dismiss-research-suggestion`), {
    method: "POST",
  });
  await expectOk(response, "Dismiss event suggestion failed");
  return response.json();
}

export async function dismissQuestionById(questionId: number): Promise<void> {
  await fetch(toAbsoluteApiUrl(`/api/questions/${questionId}/dismiss`), { method: "POST" });
}

export async function saveMainCharacterName(value: string | null): Promise<void> {
  await fetch(toAbsoluteApiUrl("/api/settings/main_character_name"), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
}

export async function reanalyzeMemoryById(memoryId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/memories/${memoryId}/reanalyze`), {
    method: "POST",
  });
  await expectOk(response, "Reanalyze failed");
}

export async function researchMemoryById(memoryId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/memories/${memoryId}/research`), {
    method: "POST",
  });
  await expectOk(response, "Research failed");
}

export async function applyResearchSuggestionById(memoryId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/memories/${memoryId}/apply-research-suggestion`), {
    method: "POST",
  });
  await expectOk(response, "Apply failed");
}

export async function dismissResearchSuggestionById(memoryId: number): Promise<void> {
  await fetch(toAbsoluteApiUrl(`/api/memories/${memoryId}/dismiss-research-suggestion`), {
    method: "POST",
  });
}

export async function deleteMemoryById(memoryId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/memories/${memoryId}`), {
    method: "DELETE",
  });
  await expectOk(response, "Delete failed");
}

export async function assignRecorderPerson(memoryId: number, personId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/memories/${memoryId}/recorder`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ person_id: personId }),
  });
  await expectOk(response, "Recorder update failed");
}

export async function mergePeopleEntries(sourceId: number, intoId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/people/${sourceId}/merge`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ into_person_id: intoId }),
  });
  await expectOk(response, "Merge failed");
}

export async function splitPersonEntry(
  sourceId: number,
  newNames: string[],
  keepAlias: boolean,
): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/people/${sourceId}/split`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ new_names: newNames, keep_alias: keepAlias }),
  });
  await expectOk(response, "Split failed");
}

export async function addPersonAlias(personId: number, alias: string): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/people/${personId}/aliases`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ alias }),
  });
  await expectOk(response, "Add alias failed");
}

export async function removePersonAlias(personId: number, alias: string): Promise<void> {
  const response = await fetch(
    toAbsoluteApiUrl(`/api/people/${personId}/aliases/${encodeURIComponent(alias)}`),
    { method: "DELETE" },
  );
  await expectOk(response, "Remove alias failed");
}

export async function createDirectoryEntry(kind: "people" | "places", name: string): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/${kind}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  await expectOk(response, "Create failed");
}

export async function renameDirectoryEntry(
  kind: "people" | "places",
  itemId: number,
  name: string,
): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/${kind}/${itemId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  await expectOk(response, "Rename failed");
}

export async function deleteDirectoryEntry(kind: "people" | "places", itemId: number): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/${kind}/${itemId}`), {
    method: "DELETE",
  });
  await expectOk(response, "Delete failed");
}

/**
 * Upload an audio recording as a memory.
 * quickCapture marks one-tap home-screen captures so backend can apply quick-entry automation.
 */
export async function createMemoryFromAudioBlob(
  blob: Blob,
  eventId?: number,
  quickCapture = false,
): Promise<MemoryEntry> {
  const formData = new FormData();
  formData.append("audio", blob, `memory-${Date.now()}.webm`);
  if (eventId !== undefined) {
    formData.append("event_id", String(eventId));
  }
  if (quickCapture) {
    formData.append("quick_capture", "true");
  }

  const response = await fetch(toAbsoluteApiUrl("/api/memories"), {
    method: "POST",
    body: formData,
  });
  await expectOk(response, "Upload failed");
  return response.json();
}

export async function answerQuestionWithMemory(questionId: number, answerMemoryId: number): Promise<void> {
  await fetch(toAbsoluteApiUrl(`/api/questions/${questionId}/answer`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer_memory_id: answerMemoryId }),
  });
}

export async function updateMemoryTitle(memoryId: number, eventDescription: string): Promise<void> {
  const response = await fetch(toAbsoluteApiUrl(`/api/memories/${memoryId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_description: eventDescription }),
  });
  await expectOk(response, "Failed to update memory title");
}

export async function createMemoryFromDocument(formData: FormData, eventId?: number): Promise<MemoryEntry> {
  if (eventId !== undefined) {
    formData.append("event_id", String(eventId));
  }
  const response = await fetch(toAbsoluteApiUrl("/api/memories/document"), {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(errorData.detail || "Upload failed");
  }

  return response.json();
}
