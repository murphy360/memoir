"use client";

import { ClipboardEventHandler, DragEventHandler, useEffect, useRef, useState } from "react";
import { DirectoryManager } from "./components/DirectoryManager";
import { MemoryCard } from "./components/MemoryCard";
import { AssetEntry, DirectoryEntry, LifeEvent, MemoryEntry, Question, AppSettings, LifePeriod } from "./types";

type PendingRecording = {
  id: string;
  audioUrl: string;
  sizeBytes: number;
  status: "recorded" | "processing" | "saved" | "failed";
  error?: string;
};

type AudioInputDevice = {
  deviceId: string;
  label: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";
const AUDIO_DEVICE_STORAGE_KEY = "memoir:last-audio-device-id";
const CLIPBOARD_IMAGE_EXTENSIONS: Record<string, string> = {
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/jpg": ".jpg",
  "image/gif": ".gif",
  "image/webp": ".webp",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function resolveApiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE}${path}`;
}

function normalizeQuestionText(value: string): string {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

function dedupeQuestions(items: Question[]): Question[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = normalizeQuestionText(item.text);
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export default function HomePage() {
  const [isRecording, setIsRecording] = useState(false);
  const [status, setStatus] = useState("Ready to record a memory.");
  const [timeline, setTimeline] = useState<MemoryEntry[]>([]);
  const [lifePeriods, setLifePeriods] = useState<LifePeriod[]>([]);
  const [lifeEvents, setLifeEvents] = useState<LifeEvent[]>([]);
  const [unlinkedAssets, setUnlinkedAssets] = useState<AssetEntry[]>([]);
  const [activeEventId, setActiveEventId] = useState<number | null>(null);
  const [activeEventAssets, setActiveEventAssets] = useState<AssetEntry[]>([]);
  const [isSavingLifeStructure, setIsSavingLifeStructure] = useState(false);
  const [isUploadingAsset, setIsUploadingAsset] = useState(false);
  const [assetLinkTargets, setAssetLinkTargets] = useState<Record<number, string>>({});
  const [eventMergeTargets, setEventMergeTargets] = useState<Record<number, string>>({});
  const [newPeriodTitle, setNewPeriodTitle] = useState("");
  const [newPeriodStart, setNewPeriodStart] = useState("");
  const [newPeriodEnd, setNewPeriodEnd] = useState("");
  const [newPeriodSummary, setNewPeriodSummary] = useState("");
  const [newEventTitle, setNewEventTitle] = useState("");
  const [newEventDateText, setNewEventDateText] = useState("");
  const [newEventDescription, setNewEventDescription] = useState("");
  const [newEventPeriodId, setNewEventPeriodId] = useState("");
  const [assetUploadNotes, setAssetUploadNotes] = useState("");
  const [peopleDirectory, setPeopleDirectory] = useState<DirectoryEntry[]>([]);
  const [placesDirectory, setPlacesDirectory] = useState<DirectoryEntry[]>([]);
  const [pendingRecording, setPendingRecording] = useState<PendingRecording | null>(null);
  const [audioDevices, setAudioDevices] = useState<AudioInputDevice[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [audioLevel, setAudioLevel] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [memoryActionId, setMemoryActionId] = useState<number | null>(null);
  const [directoryBusyKey, setDirectoryBusyKey] = useState<string | null>(null);

  const [questions, setQuestions] = useState<Question[]>([]);
  const [activeQuestion, setActiveQuestion] = useState<Question | null>(null);

  // undefined = not yet loaded, null = loaded but not set, string = set
  const [mainCharacterName, setMainCharacterName] = useState<string | null | undefined>(undefined);
  const [showCharacterInput, setShowCharacterInput] = useState(false);
  const [characterInputValue, setCharacterInputValue] = useState("");
  const [isSavingCharacter, setIsSavingCharacter] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const [isUploadingDocument, setIsUploadingDocument] = useState(false);
  const [isReadingClipboard, setIsReadingClipboard] = useState(false);
  const [isDragOverDocumentTarget, setIsDragOverDocumentTarget] = useState(false);
  const [documentUploadError, setDocumentUploadError] = useState<string | null>(null);
  const documentFileInputRef = useRef<HTMLInputElement | null>(null);
  const eventAssetInputRef = useRef<HTMLInputElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const shouldDiscardRecordingRef = useRef(false);
  const currentPreviewAudioUrlRef = useRef<string | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const levelAnimationRef = useRef<number | null>(null);
  const documentDragDepthRef = useRef(0);

  async function loadTimeline() {
    try {
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
        fetch(`${API_BASE}/api/memories`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/questions`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/people`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/places`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/settings`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/periods`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/events`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/assets/unlinked`, { cache: "no-store" }),
      ]);
      if (!memoriesRes.ok) {
        throw new Error("Failed to load timeline");
      }
      const data: MemoryEntry[] = await memoriesRes.json();
      setTimeline(data);
      if (questionsRes.ok) {
        const questionsData: Question[] = await questionsRes.json();
        setQuestions(dedupeQuestions(questionsData));
      }
      if (peopleRes.ok) {
        const peopleData: DirectoryEntry[] = await peopleRes.json();
        setPeopleDirectory(peopleData);
      }
      if (placesRes.ok) {
        const placesData: DirectoryEntry[] = await placesRes.json();
        setPlacesDirectory(placesData);
      }
      if (settingsRes.ok) {
        const settingsData: AppSettings = await settingsRes.json();
        setMainCharacterName(settingsData.main_character_name);
      }
      if (periodsRes.ok) {
        const periodData: LifePeriod[] = await periodsRes.json();
        setLifePeriods(periodData);
      }
      if (eventsRes.ok) {
        const eventData: LifeEvent[] = await eventsRes.json();
        setLifeEvents(eventData);
      }
      if (unlinkedAssetsRes.ok) {
        const assetData: AssetEntry[] = await unlinkedAssetsRes.json();
        setUnlinkedAssets(assetData);
      }
    } catch (error) {
      setStatus("Could not load timeline from API.");
    }
  }

  async function loadAssetsForEvent(eventId: number) {
    try {
      const response = await fetch(`${API_BASE}/api/events/${eventId}/assets`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error("Failed to load event assets");
      }
      const assets: AssetEntry[] = await response.json();
      setActiveEventAssets(assets);
    } catch {
      setStatus("Could not load assets for the selected event.");
      setActiveEventAssets([]);
    }
  }

  async function createLifePeriod() {
    if (!newPeriodTitle.trim()) {
      return;
    }
    setIsSavingLifeStructure(true);
    setStatus("Creating period...");
    try {
      const response = await fetch(`${API_BASE}/api/periods`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: newPeriodTitle.trim(),
          start_date_text: newPeriodStart.trim() || null,
          end_date_text: newPeriodEnd.trim() || null,
          summary: newPeriodSummary.trim() || null,
        }),
      });
      if (!response.ok) {
        throw new Error("Create period failed");
      }
      setNewPeriodTitle("");
      setNewPeriodStart("");
      setNewPeriodEnd("");
      setNewPeriodSummary("");
      await loadTimeline();
      setStatus("Period created.");
    } catch {
      setStatus("Failed to create period.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function createLifeEvent() {
    if (!newEventTitle.trim()) {
      return;
    }
    setIsSavingLifeStructure(true);
    setStatus("Creating event...");
    try {
      const response = await fetch(`${API_BASE}/api/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: newEventTitle.trim(),
          period_id: newEventPeriodId ? Number(newEventPeriodId) : null,
          description: newEventDescription.trim() || null,
          event_date_text: newEventDateText.trim() || null,
        }),
      });
      if (!response.ok) {
        throw new Error("Create event failed");
      }
      setNewEventTitle("");
      setNewEventDateText("");
      setNewEventDescription("");
      await loadTimeline();
      setStatus("Event created.");
    } catch {
      setStatus("Failed to create event.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function uploadAssetToActiveEvent(file: File) {
    if (!activeEventId) {
      return;
    }
    setIsUploadingAsset(true);
    setStatus("Uploading asset to event...");
    try {
      const formData = new FormData();
      const kind = file.type.startsWith("audio/") ? "audio" : file.type.startsWith("image/") ? "photo" : "document";
      formData.append("file", file, file.name);
      formData.append("kind", kind);
      formData.append("event_id", `${activeEventId}`);
      if (assetUploadNotes.trim()) {
        formData.append("notes", assetUploadNotes.trim());
      }

      const response = await fetch(`${API_BASE}/api/assets`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Upload asset failed");
      }

      setAssetUploadNotes("");
      if (eventAssetInputRef.current) {
        eventAssetInputRef.current.value = "";
      }
      await Promise.all([loadTimeline(), loadAssetsForEvent(activeEventId)]);
      setStatus("Asset uploaded and linked to event.");
    } catch {
      setStatus("Failed to upload asset to event.");
    } finally {
      setIsUploadingAsset(false);
    }
  }

  async function linkUnlinkedAssetToEvent(assetId: number) {
    const target = assetLinkTargets[assetId];
    if (!target) {
      return;
    }

    setIsSavingLifeStructure(true);
    setStatus("Linking asset to event...");
    try {
      const response = await fetch(`${API_BASE}/api/assets/${assetId}/link-event/${target}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ relation_type: "evidence" }),
      });
      if (!response.ok) {
        throw new Error("Link asset failed");
      }

      setAssetLinkTargets((current) => {
        const next = { ...current };
        delete next[assetId];
        return next;
      });
      await loadTimeline();
      if (activeEventId) {
        await loadAssetsForEvent(activeEventId);
      }
      setStatus("Asset linked to event.");
    } catch {
      setStatus("Failed to link asset to event.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function deleteLifeEvent(eventId: number) {
    if (!window.confirm("Delete this event from the life timeline?")) {
      return;
    }

    setIsSavingLifeStructure(true);
    setStatus("Deleting event...");
    try {
      const response = await fetch(`${API_BASE}/api/events/${eventId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error("Delete event failed");
      }

      if (activeEventId === eventId) {
        setActiveEventId(null);
        setActiveEventAssets([]);
      }
      await loadTimeline();
      setStatus("Event deleted.");
    } catch {
      setStatus("Failed to delete event.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function mergeLifeEvent(sourceId: number) {
    const targetId = eventMergeTargets[sourceId];
    if (!targetId) {
      return;
    }

    setIsSavingLifeStructure(true);
    setStatus("Merging event...");
    try {
      const response = await fetch(`${API_BASE}/api/events/${sourceId}/merge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ into_event_id: Number(targetId) }),
      });
      if (!response.ok) {
        throw new Error("Merge event failed");
      }

      const merged: LifeEvent = await response.json();
      setEventMergeTargets((current) => {
        const next = { ...current };
        delete next[sourceId];
        return next;
      });
      setActiveEventId(merged.id);
      await Promise.all([loadTimeline(), loadAssetsForEvent(merged.id)]);
      setStatus("Event merged.");
    } catch {
      setStatus("Failed to merge event.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  useEffect(() => {
    loadTimeline();
  }, []);

  async function dismissQuestion(questionId: number) {
    try {
      await fetch(`${API_BASE}/api/questions/${questionId}/dismiss`, { method: "POST" });
      setQuestions((current) => current.filter((q) => q.id !== questionId));
    } catch {
      // silently ignore dismiss errors
    }
  }

  async function saveMainCharacterName(name: string | null) {
    setIsSavingCharacter(true);
    try {
      await fetch(`${API_BASE}/api/settings/main_character_name`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: name }),
      });
      setMainCharacterName(name);
      setShowCharacterInput(false);
      setCharacterInputValue("");
    } catch {
      // ignore errors silently
    } finally {
      setIsSavingCharacter(false);
    }
  }

  async function reanalyzeMemory(memoryId: number) {
    setMemoryActionId(memoryId);
    setStatus("Reanalyzing memory...");
    try {
      const response = await fetch(`${API_BASE}/api/memories/${memoryId}/reanalyze`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error("Reanalyze failed");
      }
      await loadTimeline();
      setStatus("Memory reanalyzed.");
    } catch {
      setStatus("Failed to reanalyze memory.");
    } finally {
      setMemoryActionId(null);
    }
  }

  async function researchMemory(memoryId: number) {
    setMemoryActionId(memoryId);
    setStatus("Researching memory...");
    try {
      const response = await fetch(`${API_BASE}/api/memories/${memoryId}/research`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error("Research failed");
      }
      await loadTimeline();
      setStatus("Memory research updated.");
    } catch {
      setStatus("Failed to research memory.");
    } finally {
      setMemoryActionId(null);
    }
  }

  async function acceptResearchSuggestion(memoryId: number) {
    setMemoryActionId(memoryId);
    setStatus("Applying suggestion...");
    try {
      const response = await fetch(`${API_BASE}/api/memories/${memoryId}/apply-research-suggestion`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error("Apply failed");
      }
      await loadTimeline();
      setStatus("Date updated from research.");
    } catch {
      setStatus("Failed to apply suggestion.");
    } finally {
      setMemoryActionId(null);
    }
  }

  async function dismissResearchSuggestion(memoryId: number) {
    setMemoryActionId(memoryId);
    try {
      await fetch(`${API_BASE}/api/memories/${memoryId}/dismiss-research-suggestion`, {
        method: "POST",
      });
      await loadTimeline();
    } catch {
      // ignore
    } finally {
      setMemoryActionId(null);
    }
  }

  async function deleteMemory(memoryId: number) {
    if (!window.confirm("Delete this memory permanently?")) {
      return;
    }

    setMemoryActionId(memoryId);
    setStatus("Deleting memory...");
    try {
      const response = await fetch(`${API_BASE}/api/memories/${memoryId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error("Delete failed");
      }
      await loadTimeline();
      setStatus("Memory deleted.");
    } catch {
      setStatus("Failed to delete memory.");
    } finally {
      setMemoryActionId(null);
    }
  }

  async function assignRecorder(memoryId: number, personId: number) {
    setMemoryActionId(memoryId);
    setStatus("Saving recorder...");
    try {
      const response = await fetch(`${API_BASE}/api/memories/${memoryId}/recorder`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ person_id: personId }),
      });
      if (!response.ok) {
        throw new Error("Recorder update failed");
      }
      await loadTimeline();
      setStatus("Recorder saved.");
    } catch {
      setStatus("Failed to save recorder.");
    } finally {
      setMemoryActionId(null);
    }
  }

  async function mergePersonEntry(sourceId: number, intoId: number) {
    setDirectoryBusyKey(`people:merge:${sourceId}`);
    setStatus("Merging people...");
    try {
      const response = await fetch(`${API_BASE}/api/people/${sourceId}/merge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ into_person_id: intoId }),
      });
      if (!response.ok) {
        throw new Error("Merge failed");
      }
      await loadTimeline();
      setStatus("People merged.");
    } catch {
      setStatus("Failed to merge people.");
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function splitPersonEntry(sourceId: number, newNames: string[], keepAlias: boolean) {
    setDirectoryBusyKey(`people:split:${sourceId}`);
    setStatus("Splitting person...");
    try {
      const response = await fetch(`${API_BASE}/api/people/${sourceId}/split`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_names: newNames, keep_alias: keepAlias }),
      });
      if (!response.ok) {
        throw new Error("Split failed");
      }
      await loadTimeline();
      setStatus("Person split.");
    } catch {
      setStatus("Failed to split person.");
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function addPersonAlias(personId: number, alias: string) {
    setDirectoryBusyKey(`people:alias:${personId}`);
    try {
      const response = await fetch(`${API_BASE}/api/people/${personId}/aliases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alias }),
      });
      if (!response.ok) {
        throw new Error("Add alias failed");
      }
      await loadTimeline();
      setStatus("Alias saved.");
    } catch {
      setStatus("Failed to save alias.");
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function removePersonAlias(personId: number, alias: string) {
    setDirectoryBusyKey(`people:alias:${personId}`);
    try {
      const response = await fetch(
        `${API_BASE}/api/people/${personId}/aliases/${encodeURIComponent(alias)}`,
        { method: "DELETE" }
      );
      if (!response.ok) {
        throw new Error("Remove alias failed");
      }
      await loadTimeline();
      setStatus("Alias removed.");
    } catch {
      setStatus("Failed to remove alias.");
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function createDirectoryEntry(kind: "people" | "places", name: string) {
    setDirectoryBusyKey(`${kind}:create`);
    setStatus(`Adding ${kind === "people" ? "person" : "place"}...`);
    try {
      const response = await fetch(`${API_BASE}/api/${kind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!response.ok) {
        throw new Error("Create failed");
      }
      await loadTimeline();
      setStatus(`${kind === "people" ? "Person" : "Place"} saved.`);
    } catch {
      setStatus(`Failed to save ${kind === "people" ? "person" : "place"}.`);
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function renameDirectoryEntry(kind: "people" | "places", itemId: number, name: string) {
    setDirectoryBusyKey(`${kind}:rename:${itemId}`);
    setStatus(`Renaming ${kind === "people" ? "person" : "place"}...`);
    try {
      const response = await fetch(`${API_BASE}/api/${kind}/${itemId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!response.ok) {
        throw new Error("Rename failed");
      }
      await loadTimeline();
      setStatus(`${kind === "people" ? "Person" : "Place"} renamed.`);
    } catch {
      setStatus(`Failed to rename ${kind === "people" ? "person" : "place"}.`);
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function deleteDirectoryEntry(kind: "people" | "places", itemId: number) {
    if (!window.confirm(`Delete this ${kind === "people" ? "person" : "place"} from the directory?`)) {
      return;
    }

    setDirectoryBusyKey(`${kind}:delete:${itemId}`);
    setStatus(`Deleting ${kind === "people" ? "person" : "place"}...`);
    try {
      const response = await fetch(`${API_BASE}/api/${kind}/${itemId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error("Delete failed");
      }
      await loadTimeline();
      setStatus(`${kind === "people" ? "Person" : "Place"} deleted.`);
    } catch {
      setStatus(`Failed to delete ${kind === "people" ? "person" : "place"}.`);
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function refreshAudioDevices() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const inputs = devices
        .filter((device) => device.kind === "audioinput")
        .map((device, index) => ({
          deviceId: device.deviceId,
          label: device.label || `Microphone ${index + 1}`,
        }));

      setAudioDevices(inputs);
      setSelectedDeviceId((current) => {
        if (current && inputs.some((item) => item.deviceId === current)) {
          return current;
        }

        const savedDeviceId = localStorage.getItem(AUDIO_DEVICE_STORAGE_KEY);
        if (savedDeviceId && inputs.some((item) => item.deviceId === savedDeviceId)) {
          return savedDeviceId;
        }

        const fallbackDeviceId = inputs[0]?.deviceId || "";
        if (fallbackDeviceId) {
          localStorage.setItem(AUDIO_DEVICE_STORAGE_KEY, fallbackDeviceId);
        } else {
          localStorage.removeItem(AUDIO_DEVICE_STORAGE_KEY);
        }
        return fallbackDeviceId;
      });
    } catch {
      setStatus("Unable to enumerate microphone devices.");
    }
  }

  useEffect(() => {
    refreshAudioDevices();

    const mediaDevices = navigator.mediaDevices;
    const onDeviceChange = () => {
      refreshAudioDevices();
    };

    mediaDevices.addEventListener("devicechange", onDeviceChange);
    return () => {
      mediaDevices.removeEventListener("devicechange", onDeviceChange);
    };
  }, []);

  function stopAudioLevelMonitoring() {
    if (levelAnimationRef.current !== null) {
      cancelAnimationFrame(levelAnimationRef.current);
      levelAnimationRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    setAudioLevel(0);
  }

  function startAudioLevelMonitoring(stream: MediaStream) {
    stopAudioLevelMonitoring();

    const context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    audioContextRef.current = context;

    const data = new Uint8Array(analyser.fftSize);

    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) {
        const normalized = (data[i] - 128) / 128;
        sum += normalized * normalized;
      }
      const rms = Math.sqrt(sum / data.length);
      const scaled = Math.min(1, rms * 4);
      setAudioLevel(scaled);
      levelAnimationRef.current = requestAnimationFrame(tick);
    };

    levelAnimationRef.current = requestAnimationFrame(tick);
  }

  useEffect(() => {
    return () => {
      if (currentPreviewAudioUrlRef.current) {
        URL.revokeObjectURL(currentPreviewAudioUrlRef.current);
      }
      stopAudioLevelMonitoring();
    };
  }, []);

  async function startRecording() {
    try {
      shouldDiscardRecordingRef.current = false;
      const audioConstraint = selectedDeviceId
        ? { deviceId: { exact: selectedDeviceId } }
        : true;
      const stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraint });
      streamRef.current = stream;
      chunksRef.current = [];
      startAudioLevelMonitoring(stream);

      await refreshAudioDevices();

      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        const shouldDiscard = shouldDiscardRecordingRef.current;
        shouldDiscardRecordingRef.current = false;

        if (shouldDiscard) {
          chunksRef.current = [];
          setStatus(
            activeQuestion
              ? "Recording canceled. Your question is still waiting for an answer."
              : "Recording canceled.",
          );
          return;
        }

        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const nextAudioUrl = URL.createObjectURL(blob);
        const nextPendingId = `${Date.now()}`;

        setPendingRecording((current) => {
          if (current?.audioUrl) {
            URL.revokeObjectURL(current.audioUrl);
          }
          currentPreviewAudioUrlRef.current = nextAudioUrl;
          return {
            id: nextPendingId,
            audioUrl: nextAudioUrl,
            sizeBytes: blob.size,
            status: "recorded",
          };
        });

        setStatus("Audio recorded. You can play it now while we process it.");
        await uploadRecording(blob, nextPendingId);
      };

      recorder.start();
      setIsRecording(true);
      setStatus("Recording in progress...");
    } catch (error) {
      setStatus("Microphone permission denied or unavailable.");
    }
  }

  function stopRecording() {
    shouldDiscardRecordingRef.current = false;
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }

    streamRef.current?.getTracks().forEach((track) => track.stop());
    stopAudioLevelMonitoring();
    setIsRecording(false);
    setStatus("Finalizing audio clip...");
  }

  function cancelRecording() {
    shouldDiscardRecordingRef.current = true;
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }

    streamRef.current?.getTracks().forEach((track) => track.stop());
    stopAudioLevelMonitoring();
    setIsRecording(false);
    setStatus("Canceling recording...");
  }

  async function uploadRecording(blob: Blob, pendingId: string) {
    setIsLoading(true);
    setPendingRecording((current) =>
      current && current.id === pendingId
        ? {
            ...current,
            status: "processing",
            error: undefined,
          }
        : current,
    );

    try {
      const formData = new FormData();
      formData.append("audio", blob, `memory-${Date.now()}.webm`);

      const response = await fetch(`${API_BASE}/api/memories`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Upload failed");
      }

      const created: MemoryEntry = await response.json();
      if (activeQuestion) {
        try {
          await fetch(`${API_BASE}/api/questions/${activeQuestion.id}/answer`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ answer_memory_id: created.id }),
          });
        } catch {
          // ignore answer errors
        }
        setActiveQuestion(null);
      }
      await loadTimeline();
      setStatus("Memory saved and analyzed.");
      setPendingRecording((current) =>
        current && current.id === pendingId
          ? {
              ...current,
              status: "saved",
              error: undefined,
            }
          : current,
      );
    } catch (error) {
      setStatus("Failed to process recording. Check API connection.");
      setPendingRecording((current) =>
        current && current.id === pendingId
          ? {
              ...current,
              status: "failed",
              error: "Processing failed. You can still play this audio and try again.",
            }
          : current,
      );
    } finally {
      setIsLoading(false);
    }
  }

  async function uploadDocument(file: File) {
    setIsUploadingDocument(true);
    setDocumentUploadError(null);
    setStatus("Analyzing document...");
    try {
      const formData = new FormData();
      formData.append("file", file, file.name);

      const response = await fetch(`${API_BASE}/api/memories/document`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(errorData.detail || "Upload failed");
      }

      await loadTimeline();
      setStatus("Document analyzed and saved as a memory.");
      if (documentFileInputRef.current) {
        documentFileInputRef.current.value = "";
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to process document.";
      setDocumentUploadError(message);
      setStatus("Document upload failed.");
    } finally {
      setIsUploadingDocument(false);
    }
  }

  function asClipboardImageFile(blob: Blob, fallbackNamePrefix: string): File {
    const mimeType = (blob.type || "").toLowerCase();
    const extension = CLIPBOARD_IMAGE_EXTENSIONS[mimeType] || ".png";
    const timestamp = Date.now();
    const fileName = `${fallbackNamePrefix}-${timestamp}${extension}`;
    return new File([blob], fileName, { type: mimeType || "image/png" });
  }

  function extractImageFromClipboardData(data: DataTransfer | null): File | null {
    if (!data) {
      return null;
    }

    for (const item of Array.from(data.items)) {
      if (item.kind !== "file" || !item.type.startsWith("image/")) {
        continue;
      }
      const file = item.getAsFile();
      if (file) {
        return asClipboardImageFile(file, "screen-clipping");
      }
    }

    return null;
  }

  const onDocumentPasteZonePaste: ClipboardEventHandler<HTMLDivElement> = (event) => {
    if (isUploadingDocument || isRecording || isLoading) {
      return;
    }

    const imageFile = extractImageFromClipboardData(event.clipboardData);
    if (!imageFile) {
      return;
    }

    event.preventDefault();
    uploadDocument(imageFile);
  };

  function dataTransferHasFiles(dataTransfer: DataTransfer | null): boolean {
    if (!dataTransfer) {
      return false;
    }
    if (dataTransfer.files && dataTransfer.files.length > 0) {
      return true;
    }
    return Array.from(dataTransfer.items || []).some((item) => item.kind === "file");
  }

  const onDocumentDragEnter: DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    if (isUploadingDocument || isReadingClipboard || isRecording || isLoading) {
      return;
    }

    documentDragDepthRef.current += 1;
    if (dataTransferHasFiles(event.dataTransfer)) {
      setIsDragOverDocumentTarget(true);
    }
  };

  const onDocumentDragOver: DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    if (isUploadingDocument || isReadingClipboard || isRecording || isLoading) {
      return;
    }

    if (dataTransferHasFiles(event.dataTransfer)) {
      event.dataTransfer.dropEffect = "copy";
      setIsDragOverDocumentTarget(true);
    }
  };

  const onDocumentDragLeave: DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    documentDragDepthRef.current = Math.max(0, documentDragDepthRef.current - 1);
    if (documentDragDepthRef.current === 0) {
      setIsDragOverDocumentTarget(false);
    }
  };

  const onDocumentDrop: DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    documentDragDepthRef.current = 0;
    setIsDragOverDocumentTarget(false);

    if (isUploadingDocument || isReadingClipboard || isRecording || isLoading) {
      return;
    }

    const droppedFile = event.dataTransfer.files?.[0] || null;
    if (!droppedFile) {
      setDocumentUploadError("No file detected. Drop a PDF, image, or text file.");
      return;
    }

    uploadDocument(droppedFile);
  };

  async function pasteImageFromClipboard() {
    if (!navigator.clipboard?.read) {
      setDocumentUploadError("Clipboard image reading is not available in this browser. Click the paste box and press Ctrl+V instead.");
      return;
    }

    setIsReadingClipboard(true);
    setDocumentUploadError(null);

    try {
      const items = await navigator.clipboard.read();
      let matchedBlob: Blob | null = null;

      for (const item of items) {
        const imageType = item.types.find((type) => type.startsWith("image/"));
        if (!imageType) {
          continue;
        }
        matchedBlob = await item.getType(imageType);
        break;
      }

      if (!matchedBlob) {
        setDocumentUploadError("No image found in clipboard. Copy a screen clipping, then try again.");
        return;
      }

      await uploadDocument(asClipboardImageFile(matchedBlob, "screen-clipping"));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not read from clipboard.";
      setDocumentUploadError(message);
    } finally {
      setIsReadingClipboard(false);
    }
  }

  return (
    <main>
      <section className="hero">
        <h1>{mainCharacterName ? `${mainCharacterName}'s Memoir` : "Memoir MVP"}</h1>
        <p>Record a memory, extract a timeline clue, and get one follow-up question.</p>
        <p className="meta">Tip: start each recording with your name, where this memory happened, and when it happened (even if you only remember the year or decade).</p>
      </section>

      <section className="panel">
        <div className="inputSection">
          <label className="meta" htmlFor="mic-select">Input device</label>
          <select
            id="mic-select"
            className="micSelect"
            value={selectedDeviceId}
            onChange={(event) => {
              const nextDeviceId = event.target.value;
              setSelectedDeviceId(nextDeviceId);
              if (nextDeviceId) {
                localStorage.setItem(AUDIO_DEVICE_STORAGE_KEY, nextDeviceId);
              } else {
                localStorage.removeItem(AUDIO_DEVICE_STORAGE_KEY);
              }
            }}
            disabled={isRecording || isLoading || audioDevices.length === 0}
          >
            {audioDevices.length === 0 && <option value="">No microphones found</option>}
            {audioDevices.map((device) => (
              <option key={device.deviceId} value={device.deviceId}>
                {device.label}
              </option>
            ))}
          </select>

          <div className="levelWrap" aria-label="audio input level">
            <div className="levelTrack">
              <div className="levelFill" style={{ width: `${Math.round(audioLevel * 100)}%` }} />
            </div>
            <span className="meta levelText">Input level: {Math.round(audioLevel * 100)}%</span>
          </div>
        </div>

        {activeQuestion && (
          <div className="activePrompt">
            <div className="activePromptBody">
              <p className="activePromptLabel">Answering:</p>
              <p className="activePromptText">{activeQuestion.text}</p>
            </div>
            <button
              className="ghost"
              type="button"
              onClick={() => setActiveQuestion(null)}
              disabled={isRecording}
            >
              Cancel
            </button>
          </div>
        )}

        <div className="controls">
          <button
            className="primary"
            onClick={startRecording}
            disabled={isRecording || isLoading || audioDevices.length === 0}
            type="button"
          >
            Start Recording
          </button>
          <button
            className="secondary"
            onClick={stopRecording}
            disabled={!isRecording || isLoading}
            type="button"
          >
            Stop & Process
          </button>
          <button
            className="ghost"
            onClick={cancelRecording}
            disabled={!isRecording || isLoading}
            type="button"
          >
            Cancel Recording
          </button>
        </div>
        <p className="status">{status}</p>
      </section>

      <section className="panel">
        <h2>Upload a Document</h2>
        <p className="meta">Upload a PDF, image, or text file, or paste a screen clipping — Gemini will analyze it and save it as a memory entry.</p>
        <div className="controls">
          <input
            ref={documentFileInputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.txt"
            disabled={isUploadingDocument || isReadingClipboard || isRecording || isLoading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                uploadDocument(file);
              }
            }}
            style={{ flex: 1 }}
          />
          <button
            className="secondary"
            type="button"
            onClick={pasteImageFromClipboard}
            disabled={isUploadingDocument || isReadingClipboard || isRecording || isLoading}
          >
            Paste from Clipboard
          </button>
        </div>
        <div
          className={`pasteTarget ${isDragOverDocumentTarget ? "dragOver" : ""}`}
          role="button"
          tabIndex={0}
          onPaste={onDocumentPasteZonePaste}
          onDragEnter={onDocumentDragEnter}
          onDragOver={onDocumentDragOver}
          onDragLeave={onDocumentDragLeave}
          onDrop={onDocumentDrop}
          aria-label="Paste image from clipboard"
        >
          <p className="pasteTargetTitle">Paste or Drop a File</p>
          <p className="meta">Click this area and press Ctrl+V (or Cmd+V on Mac), or drag and drop a PDF, image, or text file here.</p>
        </div>
        {(isUploadingDocument || isReadingClipboard) && <p className="status">Analyzing document with Gemini...</p>}
        {documentUploadError && <p className="status" style={{ color: "var(--error, #c00)" }}>{documentUploadError}</p>}
      </section>

      <section className="directoryGrid">
        <DirectoryManager
          title="People Directory"
          addLabel="Add a person"
          emptyLabel="No people have been added yet."
          items={peopleDirectory}
          isBusy={directoryBusyKey !== null || isLoading || isRecording}
          onCreate={(name) => createDirectoryEntry("people", name)}
          onRename={(itemId, name) => renameDirectoryEntry("people", itemId, name)}
          onDelete={(itemId) => deleteDirectoryEntry("people", itemId)}
          onMerge={mergePersonEntry}
          onSplit={splitPersonEntry}
          onAddAlias={addPersonAlias}
          onRemoveAlias={removePersonAlias}
        />
        <DirectoryManager
          title="Places Directory"
          addLabel="Add a place"
          emptyLabel="No places have been added yet."
          items={placesDirectory}
          isBusy={directoryBusyKey !== null || isLoading || isRecording}
          onCreate={(name) => createDirectoryEntry("places", name)}
          onRename={(itemId, name) => renameDirectoryEntry("places", itemId, name)}
          onDelete={(itemId) => deleteDirectoryEntry("places", itemId)}
        />
      </section>

      <section className="panel" style={{ marginTop: "1rem" }}>
        <h2>Life Periods (beta)</h2>
        <p className="meta">Create periods and events, then attach files directly to an event or link unlinked assets from the inbox.</p>

        <div className="lifeFormGrid">
          <article className="memory">
            <h3>Create Period</h3>
            <div className="lifeFormFields">
              <input
                className="directoryInput"
                type="text"
                placeholder="Period title (e.g. Bahrain Deployment)"
                value={newPeriodTitle}
                onChange={(e) => setNewPeriodTitle(e.target.value)}
                disabled={isSavingLifeStructure || isRecording || isLoading}
              />
              <input
                className="directoryInput"
                type="text"
                placeholder="Start text (e.g. 2021)"
                value={newPeriodStart}
                onChange={(e) => setNewPeriodStart(e.target.value)}
                disabled={isSavingLifeStructure || isRecording || isLoading}
              />
              <input
                className="directoryInput"
                type="text"
                placeholder="End text (e.g. 2022)"
                value={newPeriodEnd}
                onChange={(e) => setNewPeriodEnd(e.target.value)}
                disabled={isSavingLifeStructure || isRecording || isLoading}
              />
              <textarea
                className="directoryInput"
                placeholder="Summary"
                value={newPeriodSummary}
                onChange={(e) => setNewPeriodSummary(e.target.value)}
                disabled={isSavingLifeStructure || isRecording || isLoading}
                rows={3}
              />
            </div>
            <div className="controls">
              <button
                className="primary"
                type="button"
                onClick={createLifePeriod}
                disabled={!newPeriodTitle.trim() || isSavingLifeStructure || isRecording || isLoading}
              >
                Create Period
              </button>
            </div>
          </article>

          <article className="memory">
            <h3>Create Event</h3>
            <div className="lifeFormFields">
              <input
                className="directoryInput"
                type="text"
                placeholder="Event title (e.g. Earned FMS pin)"
                value={newEventTitle}
                onChange={(e) => setNewEventTitle(e.target.value)}
                disabled={isSavingLifeStructure || isRecording || isLoading}
              />
              <select
                className="directoryInput"
                value={newEventPeriodId}
                onChange={(e) => setNewEventPeriodId(e.target.value)}
                disabled={isSavingLifeStructure || isRecording || isLoading}
              >
                <option value="">No period</option>
                {lifePeriods.map((period) => (
                  <option key={period.id} value={period.id}>{period.title}</option>
                ))}
              </select>
              <input
                className="directoryInput"
                type="text"
                placeholder="Event date text (e.g. 2022)"
                value={newEventDateText}
                onChange={(e) => setNewEventDateText(e.target.value)}
                disabled={isSavingLifeStructure || isRecording || isLoading}
              />
              <textarea
                className="directoryInput"
                placeholder="Event description"
                value={newEventDescription}
                onChange={(e) => setNewEventDescription(e.target.value)}
                disabled={isSavingLifeStructure || isRecording || isLoading}
                rows={3}
              />
            </div>
            <div className="controls">
              <button
                className="primary"
                type="button"
                onClick={createLifeEvent}
                disabled={!newEventTitle.trim() || isSavingLifeStructure || isRecording || isLoading}
              >
                Create Event
              </button>
            </div>
          </article>
        </div>

        <div className="lifePeriodList">
          {lifePeriods.length === 0 && <p className="meta">No periods created yet.</p>}
          {lifePeriods.map((period) => {
            const eventsForPeriod = lifeEvents.filter((event) => event.period_id === period.id);
            return (
              <article key={period.id} className="memory">
                <h3>{period.title}</h3>
                <p className="meta">
                  Range: <span className="badge">{period.start_date_text || "unknown"}</span> to{" "}
                  <span className="badge">{period.end_date_text || "unknown"}</span>
                </p>
                <p className="meta">
                  Events: <span className="badge">{eventsForPeriod.length}</span> Assets: <span className="badge">{period.asset_count}</span>
                </p>
                {period.summary && <p>{period.summary}</p>}
                <div className="lifeEventList">
                  {eventsForPeriod.length === 0 && <p className="meta">No events in this period yet.</p>}
                  {eventsForPeriod.map((event) => (
                    <div key={event.id} className="lifeEventCard">
                      <div
                        className={`lifeEventRow ${activeEventId === event.id ? "isActive" : ""}`}
                        role="button"
                        tabIndex={0}
                        onClick={async () => {
                          if (activeEventId === event.id) {
                            setActiveEventId(null);
                            setActiveEventAssets([]);
                            return;
                          }
                          setActiveEventId(event.id);
                          await loadAssetsForEvent(event.id);
                        }}
                        onKeyDown={async (e) => {
                          if (e.key !== "Enter" && e.key !== " ") {
                            return;
                          }
                          e.preventDefault();
                          if (activeEventId === event.id) {
                            setActiveEventId(null);
                            setActiveEventAssets([]);
                            return;
                          }
                          setActiveEventId(event.id);
                          await loadAssetsForEvent(event.id);
                        }}
                      >
                        <div>
                          <p><strong>{event.title}</strong></p>
                          <p className="meta">Date: {event.event_date_text || "unknown"} | Linked assets: {event.linked_asset_count}</p>
                        </div>
                        <span className="badge">{activeEventId === event.id ? "Hide details" : "View details"}</span>
                      </div>

                      {activeEventId === event.id && (
                        <div className="activeEventPanel inlineEventDetails">
                          <p className="meta">
                            Managing event: <span className="badge">{event.title}</span>
                          </p>
                          <div className="lifeFormFields">
                            <input
                              ref={eventAssetInputRef}
                              type="file"
                              accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.txt,.mp3,.wav,.m4a,.ogg,.webm,audio/*"
                              disabled={isUploadingAsset || isSavingLifeStructure || isRecording || isLoading}
                              onChange={(e) => {
                                const file = e.target.files?.[0];
                                if (file) {
                                  uploadAssetToActiveEvent(file);
                                }
                              }}
                            />
                            <input
                              className="directoryInput"
                              type="text"
                              placeholder="Optional notes for this asset"
                              value={assetUploadNotes}
                              onChange={(e) => setAssetUploadNotes(e.target.value)}
                              disabled={isUploadingAsset || isSavingLifeStructure || isRecording || isLoading}
                            />
                          </div>
                          <div className="lifeEventManagementRow">
                            <select
                              className="directoryInput"
                              value={eventMergeTargets[event.id] || ""}
                              onChange={(e) => setEventMergeTargets((current) => ({ ...current, [event.id]: e.target.value }))}
                              disabled={isSavingLifeStructure}
                            >
                              <option value="">Merge into another event</option>
                              {eventsForPeriod.filter((candidate) => candidate.id !== event.id).map((candidate) => (
                                <option key={candidate.id} value={candidate.id}>{candidate.title}</option>
                              ))}
                            </select>
                            <button
                              className="secondary"
                              type="button"
                              onClick={() => mergeLifeEvent(event.id)}
                              disabled={!eventMergeTargets[event.id] || isSavingLifeStructure}
                            >
                              Merge Event
                            </button>
                            <button
                              className="ghost"
                              type="button"
                              onClick={() => deleteLifeEvent(event.id)}
                              disabled={isSavingLifeStructure}
                            >
                              Delete Event
                            </button>
                          </div>
                          {activeEventAssets.length === 0 ? (
                            <p className="meta">No assets linked to this event yet.</p>
                          ) : (
                            <div className="lifeAssetList">
                              {activeEventAssets.map((asset) => (
                                <div key={asset.id} className="lifeAssetRow">
                                  <div>
                                    <p><strong>{asset.original_filename || `Asset ${asset.id}`}</strong></p>
                                    <p className="meta">Kind: {asset.kind} {asset.size_bytes ? `| ${formatBytes(asset.size_bytes)}` : ""}</p>
                                    {asset.playback_url && (
                                      <audio
                                        controls
                                        preload="metadata"
                                        src={resolveApiUrl(asset.playback_url)}
                                        style={{ width: "100%", marginTop: "0.45rem" }}
                                      />
                                    )}
                                    {asset.text_excerpt && (
                                      <p className="meta assetTranscript">Transcript: {asset.text_excerpt}</p>
                                    )}
                                  </div>
                                  <a className="secondary linkButton" href={resolveApiUrl(asset.download_url)} target="_blank" rel="noreferrer">
                                    Open
                                  </a>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </article>
            );
          })}
        </div>

        <article className="memory" style={{ marginTop: "0.75rem" }}>
          <h3>Unlinked Assets Inbox</h3>
          {unlinkedAssets.length === 0 ? (
            <p className="meta">No unlinked assets. Great job keeping context connected.</p>
          ) : (
            <div className="lifeAssetList">
              {unlinkedAssets.map((asset) => (
                <div key={asset.id} className="lifeAssetRow">
                  <div>
                    <p><strong>{asset.original_filename || `Asset ${asset.id}`}</strong></p>
                    <p className="meta">Kind: {asset.kind} {asset.size_bytes ? `| ${formatBytes(asset.size_bytes)}` : ""}</p>
                  </div>
                  <div className="lifeAssetLinkControls">
                    <select
                      className="directoryInput"
                      value={assetLinkTargets[asset.id] || ""}
                      onChange={(e) => setAssetLinkTargets((current) => ({ ...current, [asset.id]: e.target.value }))}
                      disabled={isSavingLifeStructure || lifeEvents.length === 0}
                    >
                      <option value="">Select event</option>
                      {lifeEvents.map((event) => (
                        <option key={event.id} value={event.id}>{event.title}</option>
                      ))}
                    </select>
                    <button
                      className="secondary"
                      type="button"
                      onClick={() => linkUnlinkedAssetToEvent(asset.id)}
                      disabled={!assetLinkTargets[asset.id] || isSavingLifeStructure}
                    >
                      Link
                    </button>
                    <a className="ghost linkButton" href={resolveApiUrl(asset.download_url)} target="_blank" rel="noreferrer">
                      View
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>
      </section>

      <section className="timeline">
        {mainCharacterName === null && (
          <article className="questionCard characterPromptCard">
            <p className="questionText">Before we continue, what should we call you on your memory cards?</p>
            {showCharacterInput ? (
              <div className="characterInputRow">
                <input
                  className="characterInput"
                  type="text"
                  placeholder="Your name or nickname"
                  value={characterInputValue}
                  onChange={(e) => setCharacterInputValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && characterInputValue.trim()) {
                      saveMainCharacterName(characterInputValue.trim());
                    }
                  }}
                  autoFocus
                  disabled={isSavingCharacter}
                />
                <button
                  className="primary"
                  type="button"
                  onClick={() => {
                    if (characterInputValue.trim()) {
                      saveMainCharacterName(characterInputValue.trim());
                    }
                  }}
                  disabled={isSavingCharacter || !characterInputValue.trim()}
                >
                  Save
                </button>
                <button
                  className="ghost"
                  type="button"
                  onClick={() => {
                    setShowCharacterInput(false);
                    setCharacterInputValue("");
                  }}
                  disabled={isSavingCharacter}
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div className="questionActions">
                <button
                  className="primary"
                  type="button"
                  onClick={() => setShowCharacterInput(true)}
                >
                  Answer this
                </button>
                <button
                  className="ghost"
                  type="button"
                  onClick={() => saveMainCharacterName("")}
                >
                  Remove
                </button>
              </div>
            )}
          </article>
        )}
        {questions.length > 0 && (
          <div className="questionsSection">
            {questions.map((q) => {
              const sourceMemory = q.source_memory_id
                ? timeline.find((m) => m.id === q.source_memory_id)
                : null;
              return (
              <article key={q.id} className="questionCard">
                <p className="questionText">{q.text}</p>
                {sourceMemory && (
                  <p className="questionSource">
                    From research on: <em>{sourceMemory.event_description}</em>
                  </p>
                )}
                <div className="questionActions">
                  <button
                    className="primary"
                    type="button"
                    onClick={() => {
                      setActiveQuestion(q);
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                    disabled={isRecording || isLoading}
                  >
                    Answer this
                  </button>
                  <button
                    className="ghost"
                    type="button"
                    onClick={() => dismissQuestion(q.id)}
                    disabled={isRecording || isLoading}
                  >
                    Remove
                  </button>
                </div>
              </article>
              );
            })}
          </div>
        )}
        {pendingRecording && (
          <article className="memory">
            <h3>Latest Recording Preview</h3>
            <p className="meta">
              Status: <span className="badge">{pendingRecording.status}</span>
            </p>
            <p className="meta">File size: {formatBytes(pendingRecording.sizeBytes)}</p>
            <audio controls preload="metadata" src={pendingRecording.audioUrl} style={{ width: "100%" }} />
            {pendingRecording.sizeBytes === 0 && (
              <p className="meta">This recording is empty (0 B), which explains silent playback.</p>
            )}
            {pendingRecording.error && <p className="meta">{pendingRecording.error}</p>}
          </article>
        )}
        {timeline.map((memory) => (
          <MemoryCard
            key={memory.id}
            memory={memory}
            linkedQuestions={questions.filter((q) => q.source_memory_id === memory.id)}
            peopleOptions={peopleDirectory}
            formatBytes={formatBytes}
            resolveApiUrl={resolveApiUrl}
            onResearch={researchMemory}
            onAcceptSuggestion={acceptResearchSuggestion}
            onDismissSuggestion={dismissResearchSuggestion}
            onReanalyze={reanalyzeMemory}
            onDelete={deleteMemory}
            onAssignRecorder={assignRecorder}
            isBusy={isLoading || memoryActionId === memory.id || isRecording}
          />
        ))}
        {timeline.length === 0 && <p className="meta">No memories yet. Record your first one.</p>}
      </section>
    </main>
  );
}
