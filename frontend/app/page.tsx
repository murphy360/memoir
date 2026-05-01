"use client";

import { ClipboardEventHandler, DragEventHandler, useEffect, useRef, useState } from "react";
import { DirectoryManager } from "./components/DirectoryManager";
import { MemoryCard } from "./components/MemoryCard";
import { AssetEntry, DirectoryEntry, LifeEvent, MemoryEntry, Question, LifePeriod, LifePeriodAnalysis } from "./types";
import {
  analyzeLifePeriod,
  applyResearchSuggestionById,
  answerQuestionWithMemory,
  assignRecorderPerson,
  createDirectoryEntry as createDirectoryEntryRequest,
  createEvent,
  createMemoryFromAudioBlob,
  createMemoryFromDocument,
  createPeriod,
  deleteDirectoryEntry as deleteDirectoryEntryRequest,
  deleteEventById,
  deleteMemoryById,
  deletePeriodById,
  dismissQuestionById,
  dismissResearchSuggestionById,
  fetchEventAssets,
  fetchTimelineBundle,
  linkAssetToEvent,
  mergeEventInto,
  mergePeopleEntries,
  mergePeriodInto,
  reanalyzeMemoryById,
  removePersonAlias as removePersonAliasRequest,
  renameDirectoryEntry as renameDirectoryEntryRequest,
  renamePeriodTitle,
  resolveApiUrl,
  researchMemoryById,
  saveMainCharacterName as saveMainCharacterNameRequest,
  splitPersonEntry as splitPersonEntryRequest,
  addPersonAlias as addPersonAliasRequest,
  uploadAsset,
} from "./lib/memoirApi";
import {
  AUDIO_DEVICE_STORAGE_KEY,
  CLIPBOARD_IMAGE_EXTENSIONS,
  dedupeQuestions,
  displayPeriodSummary,
  formatBytes,
} from "./lib/memoirUi";

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

export default function HomePage() {
  const [isDirectoryDrawerOpen, setIsDirectoryDrawerOpen] = useState(false);
  const [isCaptureDrawerOpen, setIsCaptureDrawerOpen] = useState(false);
  const [activeDirectoryTab, setActiveDirectoryTab] = useState<"people" | "places">("people");
  const [directorySearch, setDirectorySearch] = useState("");
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
  const [isPeriodComposerOpen, setIsPeriodComposerOpen] = useState(false);
  const [expandedPeriods, setExpandedPeriods] = useState<Record<number, boolean>>({});
  const [eventDraftsByPeriod, setEventDraftsByPeriod] = useState<
    Record<number, { title: string; dateText: string; description: string }>
  >({});
  const [periodAnalysisById, setPeriodAnalysisById] = useState<Record<number, LifePeriodAnalysis | null>>({});
  const [periodAnalysisBusyId, setPeriodAnalysisBusyId] = useState<number | null>(null);
  const [editingPeriodTitleId, setEditingPeriodTitleId] = useState<number | null>(null);
  const [editingPeriodTitleValue, setEditingPeriodTitleValue] = useState("");
  const [mergingPeriodId, setMergingPeriodId] = useState<number | null>(null);

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
      const data = await fetchTimelineBundle();
      setTimeline(data.memories);
      if (data.questions) {
        setQuestions(dedupeQuestions(data.questions));
      }
      if (data.people) {
        setPeopleDirectory(data.people);
      }
      if (data.places) {
        setPlacesDirectory(data.places);
      }
      if (data.settings) {
        setMainCharacterName(data.settings.main_character_name);
      }
      if (data.periods) {
        setLifePeriods(data.periods);
      }
      if (data.events) {
        setLifeEvents(data.events);
      }
      if (data.unlinkedAssets) {
        setUnlinkedAssets(data.unlinkedAssets);
      }
    } catch (error) {
      setStatus("Could not load timeline from API.");
    }
  }

  async function loadAssetsForEvent(eventId: number) {
    try {
      setActiveEventAssets(await fetchEventAssets(eventId));
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
      await createPeriod({
        title: newPeriodTitle.trim(),
        start_date_text: newPeriodStart.trim() || null,
        end_date_text: newPeriodEnd.trim() || null,
        summary: newPeriodSummary.trim() || null,
      });
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

  async function createLifeEvent(options?: {
    title?: string;
    eventDateText?: string;
    description?: string;
    periodId?: number | null;
    resetPeriodDraftId?: number;
  }) {
    const title = options?.title ?? newEventTitle;
    const periodId = options?.periodId ?? (newEventPeriodId ? Number(newEventPeriodId) : null);
    const eventDateText = options?.eventDateText ?? newEventDateText;
    const description = options?.description ?? newEventDescription;

    if (!title.trim()) {
      return;
    }
    setIsSavingLifeStructure(true);
    setStatus("Creating event...");
    try {
      await createEvent({
        title: title.trim(),
        period_id: periodId,
        description: description.trim() || null,
        event_date_text: eventDateText.trim() || null,
      });
      setNewEventTitle("");
      setNewEventDateText("");
      setNewEventDescription("");
      if (options?.resetPeriodDraftId !== undefined) {
        setEventDraftsByPeriod((current) => ({
          ...current,
          [options.resetPeriodDraftId!]: {
            title: "",
            dateText: "",
            description: "",
          },
        }));
      }
      await loadTimeline();
      setStatus("Event created.");
    } catch {
      setStatus("Failed to create event.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function analyzePeriod(
    periodId: number,
    options?: { applyDates?: boolean; applyTitle?: boolean; regenerateSummary?: boolean },
  ) {
    setPeriodAnalysisBusyId(periodId);
    setStatus("Analyzing period...");
    try {
      const analysis: LifePeriodAnalysis = await analyzeLifePeriod(periodId, {
        apply_dates: Boolean(options?.applyDates),
        apply_title: Boolean(options?.applyTitle),
        regenerate_summary: Boolean(options?.regenerateSummary),
      });
      setPeriodAnalysisById((current) => ({ ...current, [periodId]: analysis }));

      if (options?.applyDates || options?.applyTitle || options?.regenerateSummary) {
        await loadTimeline();
        setStatus("Period recommendations applied.");
      } else {
        setStatus("Period analysis ready.");
      }
    } catch {
      setStatus("Failed to analyze period.");
    } finally {
      setPeriodAnalysisBusyId(null);
    }
  }

  function togglePeriodExpanded(periodId: number) {
    setExpandedPeriods((current) => ({ ...current, [periodId]: !current[periodId] }));
  }

  function updateEventDraftForPeriod(
    periodId: number,
    patch: Partial<{ title: string; dateText: string; description: string }>,
  ) {
    setEventDraftsByPeriod((current) => ({
      ...current,
      [periodId]: {
        title: current[periodId]?.title || "",
        dateText: current[periodId]?.dateText || "",
        description: current[periodId]?.description || "",
        ...patch,
      },
    }));
  }

  async function renamePeriod(periodId: number, newTitle: string) {
    const trimmed = newTitle.trim();
    if (!trimmed) return;
    setStatus("Saving period title...");
    try {
      await renamePeriodTitle(periodId, trimmed);
      setEditingPeriodTitleId(null);
      setEditingPeriodTitleValue("");
      await loadTimeline();
      setStatus("Period title updated.");
    } catch {
      setStatus("Failed to rename period.");
    }
  }

  async function deletePeriod(periodId: number, periodTitle: string) {
    if (!confirm(`Delete "${periodTitle}"? Its events and assets will be unlinked but not deleted.`)) return;
    setStatus("Deleting period...");
    try {
      await deletePeriodById(periodId);
      setPeriodAnalysisById((current) => { const next = { ...current }; delete next[periodId]; return next; });
      await loadTimeline();
      setStatus("Period deleted.");
    } catch {
      setStatus("Failed to delete period.");
    }
  }

  async function mergePeriod(fromPeriodId: number, intoPeriodId: number) {
    setMergingPeriodId(null);
    setStatus("Merging period...");
    try {
      await mergePeriodInto(fromPeriodId, intoPeriodId);
      setPeriodAnalysisById((current) => { const next = { ...current }; delete next[fromPeriodId]; return next; });
      await loadTimeline();
      setStatus("Period merged.");
    } catch {
      setStatus("Failed to merge period.");
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
      await uploadAsset(formData);

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
      await linkAssetToEvent(assetId, Number(target), "evidence");

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
      await deleteEventById(eventId);

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
      const merged: LifeEvent = await mergeEventInto(sourceId, Number(targetId));
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
      await dismissQuestionById(questionId);
      setQuestions((current) => current.filter((q) => q.id !== questionId));
    } catch {
      // silently ignore dismiss errors
    }
  }

  async function saveMainCharacterName(name: string | null) {
    setIsSavingCharacter(true);
    try {
      await saveMainCharacterNameRequest(name);
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
      await reanalyzeMemoryById(memoryId);
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
      await researchMemoryById(memoryId);
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
      await applyResearchSuggestionById(memoryId);
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
      await dismissResearchSuggestionById(memoryId);
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
      await deleteMemoryById(memoryId);
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
      await assignRecorderPerson(memoryId, personId);
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
      await mergePeopleEntries(sourceId, intoId);
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
      await splitPersonEntryRequest(sourceId, newNames, keepAlias);
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
      await addPersonAliasRequest(personId, alias);
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
      await removePersonAliasRequest(personId, alias);
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
      await createDirectoryEntryRequest(kind, name);
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
      await renameDirectoryEntryRequest(kind, itemId, name);
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
      await deleteDirectoryEntryRequest(kind, itemId);
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
      const created: MemoryEntry = await createMemoryFromAudioBlob(blob);
      if (activeQuestion) {
        try {
          await answerQuestionWithMemory(activeQuestion.id, created.id);
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
      await createMemoryFromDocument(formData);

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

  const normalizedDirectorySearch = directorySearch.trim().toLowerCase();
  const filteredPeopleDirectory = peopleDirectory.filter((entry) => {
    if (!normalizedDirectorySearch) {
      return true;
    }
    if (entry.name.toLowerCase().includes(normalizedDirectorySearch)) {
      return true;
    }
    return entry.aliases.some((alias) => alias.toLowerCase().includes(normalizedDirectorySearch));
  });
  const filteredPlacesDirectory = placesDirectory.filter((entry) => {
    if (!normalizedDirectorySearch) {
      return true;
    }
    return entry.name.toLowerCase().includes(normalizedDirectorySearch);
  });
  const activeDirectoryCount = activeDirectoryTab === "people"
    ? filteredPeopleDirectory.length
    : filteredPlacesDirectory.length;
  const activeDirectoryTotal = activeDirectoryTab === "people"
    ? peopleDirectory.length
    : placesDirectory.length;
  const lifeEventMemoryIds = new Set(
    lifeEvents
      .map((event) => event.legacy_memory_id)
      .filter((memoryId): memoryId is number => memoryId !== null),
  );
  const questionsWithContext = questions.map((question) => {
    const sourceMemory = question.source_memory_id
      ? timeline.find((memory) => memory.id === question.source_memory_id) ?? null
      : null;
    const sourceEvent = sourceMemory
      ? lifeEvents.find((event) => event.legacy_memory_id === sourceMemory.id) ?? null
      : null;
    const sourcePeriod = sourceEvent && sourceEvent.period_id !== null
      ? lifePeriods.find((period) => period.id === sourceEvent.period_id) ?? null
      : null;

    return {
      question,
      sourceMemory,
      sourceEvent,
      sourcePeriod,
    };
  });
  const questionsByEventId = new Map<number, typeof questionsWithContext>();
  const questionsByPeriodNoEvent = new Map<number, typeof questionsWithContext>();
  const questionsWithNoContext: typeof questionsWithContext = [];
  for (const item of questionsWithContext) {
    if (item.sourceEvent) {
      const list = questionsByEventId.get(item.sourceEvent.id) ?? [];
      list.push(item);
      questionsByEventId.set(item.sourceEvent.id, list);
    } else if (item.sourcePeriod) {
      const list = questionsByPeriodNoEvent.get(item.sourcePeriod.id) ?? [];
      list.push(item);
      questionsByPeriodNoEvent.set(item.sourcePeriod.id, list);
    } else {
      questionsWithNoContext.push(item);
    }
  }
  const unassignedEvents = lifeEvents.filter((event) => event.period_id === null);
  const timelineStandaloneMemories = timeline.filter((memory) => !lifeEventMemoryIds.has(memory.id));

  return (
    <main className="appShell">
      <button
        type="button"
        className="secondary directoryToggle"
        onClick={() => setIsDirectoryDrawerOpen(true)}
      >
        People & Places
      </button>

      {isDirectoryDrawerOpen && (
        <button
          type="button"
          className="directoryBackdrop"
          aria-label="Close directory panel"
          onClick={() => setIsDirectoryDrawerOpen(false)}
        />
      )}

      <aside className={`directorySidebar ${isDirectoryDrawerOpen ? "isOpen" : ""}`}>
        <div className="directorySidebarHeader">
          <div>
            <h2>Directories</h2>
            <p className="meta directoryMeta">{activeDirectoryCount} shown of {activeDirectoryTotal}</p>
          </div>
          <button
            type="button"
            className="ghost directoryClose"
            onClick={() => setIsDirectoryDrawerOpen(false)}
          >
            Close
          </button>
        </div>

        <div className="directoryTabRow" role="tablist" aria-label="Directory tabs">
          <button
            type="button"
            role="tab"
            aria-selected={activeDirectoryTab === "people"}
            className={activeDirectoryTab === "people" ? "primary" : "secondary"}
            onClick={() => setActiveDirectoryTab("people")}
          >
            People
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeDirectoryTab === "places"}
            className={activeDirectoryTab === "places" ? "primary" : "secondary"}
            onClick={() => setActiveDirectoryTab("places")}
          >
            Places
          </button>
        </div>

        <div className="directoryFilterHeaderRow">
          <label className="directoryFilterLabel" htmlFor="directory-filter-input">
            Search {activeDirectoryTab === "people" ? "people" : "places"}
          </label>
          <button
            type="button"
            className="ghost directoryFilterClear"
            onClick={() => setDirectorySearch("")}
            disabled={!directorySearch}
          >
            Clear
          </button>
        </div>
        <input
          id="directory-filter-input"
          type="search"
          className="directoryInput"
          placeholder={activeDirectoryTab === "people" ? "Type a name or alias" : "Type a place name"}
          value={directorySearch}
          onChange={(event) => setDirectorySearch(event.target.value)}
          autoComplete="off"
        />

        {activeDirectoryTab === "people" ? (
          <DirectoryManager
            title="People Directory"
            addLabel="Add a person"
            emptyLabel={normalizedDirectorySearch ? "No matching people for this search." : "No people have been added yet."}
            items={filteredPeopleDirectory}
            isBusy={directoryBusyKey !== null || isLoading || isRecording}
            onCreate={(name) => createDirectoryEntry("people", name)}
            onRename={(itemId, name) => renameDirectoryEntry("people", itemId, name)}
            onDelete={(itemId) => deleteDirectoryEntry("people", itemId)}
            onMerge={mergePersonEntry}
            onSplit={splitPersonEntry}
            onAddAlias={addPersonAlias}
            onRemoveAlias={removePersonAlias}
          />
        ) : (
          <DirectoryManager
            title="Places Directory"
            addLabel="Add a place"
            emptyLabel={normalizedDirectorySearch ? "No matching places for this search." : "No places have been added yet."}
            items={filteredPlacesDirectory}
            isBusy={directoryBusyKey !== null || isLoading || isRecording}
            onCreate={(name) => createDirectoryEntry("places", name)}
            onRename={(itemId, name) => renameDirectoryEntry("places", itemId, name)}
            onDelete={(itemId) => deleteDirectoryEntry("places", itemId)}
          />
        )}
      </aside>

      <div className="workspaceColumn">
        <section className="hero">
          <div className="heroRow">
            <h1>{mainCharacterName ? `${mainCharacterName}'s Memoir` : "Memoir MVP"}</h1>
            <button
              type="button"
              className="secondary captureToggle"
              onClick={() => setIsCaptureDrawerOpen(true)}
            >
              + New Memory
            </button>
          </div>
          <p>Explore your timeline.</p>
          <p className="meta">Tip: start each recording with your name, where this memory happened, and when it happened.</p>
        </section>

        <>
            <section className="panel" style={{ marginTop: "1rem" }}>
              <div className="periodsHeader">
                <div>
                  <h2>Life Periods</h2>
                  <p className="meta">Start with periods, expand only the one you want, and add events inside that period.</p>
                </div>
                <button
                  className="secondary"
                  type="button"
                  onClick={() => setIsPeriodComposerOpen((current) => !current)}
                >
                  {isPeriodComposerOpen ? "Hide period form" : "New period"}
                </button>
              </div>

              {isPeriodComposerOpen && (
                <article className="memory" style={{ marginTop: "0.75rem" }}>
                  <h3>Create Period</h3>
                  <div className="lifeFormFields">
                    <input
                      className="directoryInput"
                      type="text"
                      placeholder="Period title (e.g. Birth and Early Childhood)"
                      value={newPeriodTitle}
                      onChange={(e) => setNewPeriodTitle(e.target.value)}
                      disabled={isSavingLifeStructure || isRecording || isLoading}
                    />
                    <input
                      className="directoryInput"
                      type="text"
                      placeholder="Start text (e.g. 1948)"
                      value={newPeriodStart}
                      onChange={(e) => setNewPeriodStart(e.target.value)}
                      disabled={isSavingLifeStructure || isRecording || isLoading}
                    />
                    <input
                      className="directoryInput"
                      type="text"
                      placeholder="End text (e.g. 1960)"
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
                      onClick={async () => {
                        await createLifePeriod();
                        setIsPeriodComposerOpen(false);
                      }}
                      disabled={!newPeriodTitle.trim() || isSavingLifeStructure || isRecording || isLoading}
                    >
                      Create Period
                    </button>
                  </div>
                </article>
              )}

              <div className="lifePeriodList">
                {lifePeriods.length === 0 && <p className="meta">No periods created yet.</p>}
                {lifePeriods.map((period) => {
                  const eventsForPeriod = lifeEvents.filter((event) => event.period_id === period.id);
                  const eventsForPeriodIds = new Set(eventsForPeriod.map((e) => e.id));
                  const periodQuestionCount =
                    (questionsByPeriodNoEvent.get(period.id)?.length ?? 0) +
                    questionsWithContext.filter(
                      (item) => item.sourceEvent !== null && eventsForPeriodIds.has(item.sourceEvent.id),
                    ).length;
                  const isExpanded = Boolean(expandedPeriods[period.id]);
                  const draft = eventDraftsByPeriod[period.id] || {
                    title: "",
                    dateText: "",
                    description: "",
                  };
                  const periodAnalysis = periodAnalysisById[period.id] || null;

                  return (
                    <article key={period.id} className="memory">
                      <div className="periodSummaryRow">
                        <div style={{ flex: 1 }}>
                          {editingPeriodTitleId === period.id ? (
                            <div className="controls" style={{ marginBottom: "0.35rem" }}>
                              <input
                                className="directoryInput"
                                type="text"
                                value={editingPeriodTitleValue}
                                autoFocus
                                onChange={(e) => setEditingPeriodTitleValue(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") renamePeriod(period.id, editingPeriodTitleValue);
                                  if (e.key === "Escape") { setEditingPeriodTitleId(null); setEditingPeriodTitleValue(""); }
                                }}
                                style={{ flex: 1 }}
                              />
                              <button className="primary" type="button" onClick={() => renamePeriod(period.id, editingPeriodTitleValue)} disabled={!editingPeriodTitleValue.trim()}>Save</button>
                              <button className="secondary" type="button" onClick={() => { setEditingPeriodTitleId(null); setEditingPeriodTitleValue(""); }}>Cancel</button>
                            </div>
                          ) : (
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                              <h3 style={{ margin: 0 }}>{period.title}</h3>
                              <button
                                className="secondary"
                                type="button"
                                title="Edit title"
                                style={{ padding: "0.1rem 0.45rem", fontSize: "0.8rem" }}
                                onClick={() => { setEditingPeriodTitleId(period.id); setEditingPeriodTitleValue(period.title); }}
                              >
                                ✏️
                              </button>
                            </div>
                          )}
                          <p className="meta">
                            Range: <span className="badge">{period.start_date_text || "unknown"}</span> to{" "}
                            <span className="badge">{period.end_date_text || "unknown"}</span>
                          </p>
                          <p className="meta">
                            Events: <span className="badge">{eventsForPeriod.length}</span> Assets: <span className="badge">{period.asset_count}</span>{periodQuestionCount > 0 && <> Questions: <span className="badge">{periodQuestionCount}</span></>}
                          </p>
                        </div>
                        <button
                          className="secondary"
                          type="button"
                          onClick={() => togglePeriodExpanded(period.id)}
                        >
                          {isExpanded ? "Hide" : "Open"}
                        </button>
                      </div>

                      {isExpanded && (
                        <>
                          {period.summary && <p>{displayPeriodSummary(period.summary)}</p>}

                          <div className="controls" style={{ marginTop: "0.45rem" }}>
                            <button
                              className="secondary"
                              type="button"
                              onClick={() => analyzePeriod(period.id)}
                              disabled={periodAnalysisBusyId === period.id || isSavingLifeStructure || isRecording || isLoading}
                            >
                              Analyze Period
                            </button>
                            <button
                              className="secondary"
                              type="button"
                              onClick={() => analyzePeriod(period.id, { regenerateSummary: true })}
                              disabled={periodAnalysisBusyId === period.id || isSavingLifeStructure || isRecording || isLoading}
                            >
                              Generate Summary
                            </button>
                            <button
                              className="secondary"
                              type="button"
                              onClick={() => setMergingPeriodId(mergingPeriodId === period.id ? null : period.id)}
                              disabled={lifePeriods.length < 2 || isSavingLifeStructure || isRecording || isLoading}
                            >
                              Merge Into…
                            </button>
                            <button
                              className="secondary"
                              type="button"
                              style={{ color: "var(--danger, #c0392b)" }}
                              onClick={() => deletePeriod(period.id, period.title)}
                              disabled={isSavingLifeStructure || isRecording || isLoading}
                            >
                              Delete Period
                            </button>
                          {periodAnalysis && (periodAnalysis.recommended_titles.length > 0 || !periodAnalysis.coverage_ok) && (
                              <button
                                className="primary"
                                type="button"
                                onClick={() => analyzePeriod(period.id, { applyDates: true, applyTitle: true, regenerateSummary: true })}
                                disabled={periodAnalysisBusyId === period.id || isSavingLifeStructure || isRecording || isLoading}
                              >
                                Apply Top Recommendation
                              </button>
                            )}
                          </div>

                          {mergingPeriodId === period.id && (
                            <div className="controls" style={{ marginTop: "0.35rem", flexWrap: "wrap" }}>
                              <span className="meta" style={{ alignSelf: "center" }}>Move all events &amp; assets into:</span>
                              {lifePeriods
                                .filter((p) => p.id !== period.id)
                                .map((p) => (
                                  <button
                                    key={p.id}
                                    className="secondary"
                                    type="button"
                                    onClick={() => mergePeriod(period.id, p.id)}
                                  >
                                    {p.title}
                                  </button>
                                ))}
                              <button className="secondary" type="button" onClick={() => setMergingPeriodId(null)}>Cancel</button>
                            </div>
                          )}

                          {periodAnalysis && (
                            <article className="memory" style={{ marginBottom: "0.65rem" }}>
                              <h3>Period Analysis</h3>
                              <p className="meta">
                                Coverage: <span className="badge">{periodAnalysis.coverage_ok ? "Good" : "Needs update"}</span>
                              </p>
                              <p className="meta">{periodAnalysis.coverage_reasoning}</p>
                              {periodAnalysis.recommended_start_date_text && periodAnalysis.recommended_end_date_text && (
                                <p className="meta">
                                  Recommended date range: <span className="badge">{periodAnalysis.recommended_start_date_text}</span> to <span className="badge">{periodAnalysis.recommended_end_date_text}</span>
                                </p>
                              )}
                              {periodAnalysis.recommended_titles.length > 0 && (
                                <div style={{ marginTop: "0.45rem" }}>
                                  <p className="meta"><strong>Suggested titles</strong> — click one to apply it:</p>
                                  <div className="controls" style={{ flexWrap: "wrap" }}>
                                    {periodAnalysis.recommended_titles.map((title) => (
                                      <button
                                        key={title}
                                        className="secondary"
                                        type="button"
                                        style={{ fontWeight: "normal" }}
                                        onClick={async () => {
                                          await renamePeriod(period.id, title);
                                          setPeriodAnalysisById((current) => ({ ...current, [period.id]: null }));
                                        }}
                                      >
                                        {title}
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              )}
                              <p className="meta">{periodAnalysis.title_reasoning}</p>
                              {periodAnalysis.generated_summary && (
                                <>
                                  <p className="meta" style={{ marginTop: "0.55rem" }}><strong>Suggested summary</strong></p>
                                  <p>{periodAnalysis.generated_summary}</p>
                                  <p className="meta">{periodAnalysis.summary_reasoning}</p>
                                </>
                              )}
                            </article>
                          )}

                          <article className="memory" style={{ marginBottom: "0.65rem" }}>
                            <h3>Add Event to {period.title}</h3>
                            <div className="lifeFormFields">
                              <input
                                className="directoryInput"
                                type="text"
                                placeholder="Event title"
                                value={draft.title}
                                onChange={(e) => updateEventDraftForPeriod(period.id, { title: e.target.value })}
                                disabled={isSavingLifeStructure || isRecording || isLoading}
                              />
                              <input
                                className="directoryInput"
                                type="text"
                                placeholder="Event date text"
                                value={draft.dateText}
                                onChange={(e) => updateEventDraftForPeriod(period.id, { dateText: e.target.value })}
                                disabled={isSavingLifeStructure || isRecording || isLoading}
                              />
                              <textarea
                                className="directoryInput"
                                placeholder="Event description"
                                value={draft.description}
                                onChange={(e) => updateEventDraftForPeriod(period.id, { description: e.target.value })}
                                disabled={isSavingLifeStructure || isRecording || isLoading}
                                rows={3}
                              />
                            </div>
                            <div className="controls">
                              <button
                                className="primary"
                                type="button"
                                onClick={() =>
                                  createLifeEvent({
                                    title: draft.title,
                                    eventDateText: draft.dateText,
                                    description: draft.description,
                                    periodId: period.id,
                                    resetPeriodDraftId: period.id,
                                  })
                                }
                                disabled={!draft.title.trim() || isSavingLifeStructure || isRecording || isLoading}
                              >
                                Create Event
                              </button>
                            </div>
                          </article>

                          {(questionsByPeriodNoEvent.get(period.id)?.length ?? 0) > 0 && (
                            <div className="inlineQuestionList">
                              <p className="inlineQuestionListLabel">Open questions for this period</p>
                              {questionsByPeriodNoEvent.get(period.id)!.map(({ question, sourceMemory }) => (
                                <article key={question.id} className="questionCard inlineQuestionCard">
                                  <p className="questionText">{question.text}</p>
                                  {sourceMemory && (
                                    <p className="questionSource">From: <em>{sourceMemory.event_description}</em></p>
                                  )}
                                  <div className="questionActions">
                                    <button
                                      className="primary"
                                      type="button"
                                      onClick={() => { setActiveQuestion(question); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                                      disabled={isRecording || isLoading}
                                    >
                                      Answer this
                                    </button>
                                    <button
                                      className="ghost"
                                      type="button"
                                      onClick={() => dismissQuestion(question.id)}
                                      disabled={isRecording || isLoading}
                                    >
                                      Remove
                                    </button>
                                  </div>
                                </article>
                              ))}
                            </div>
                          )}

                          <div className="lifeEventList">
                            {eventsForPeriod.length === 0 && <p className="meta">No events in this period yet.</p>}
                            {eventsForPeriod.map((event) => (
                              <article key={event.id} className="memory">
                                <div className="periodSummaryRow">
                                  <div>
                                    <p style={{ margin: 0, fontWeight: 700 }}>{event.title}</p>
                                    <p className="meta">Date: {event.event_date_text || "unknown"} | Linked assets: {event.linked_asset_count}{(questionsByEventId.get(event.id)?.length ?? 0) > 0 && ` | Questions: ${questionsByEventId.get(event.id)!.length}`}</p>
                                  </div>
                                  <button
                                    className="secondary"
                                    type="button"
                                    onClick={async () => {
                                      if (activeEventId === event.id) {
                                        setActiveEventId(null);
                                        setActiveEventAssets([]);
                                        return;
                                      }
                                      setActiveEventId(event.id);
                                      await loadAssetsForEvent(event.id);
                                    }}
                                  >
                                    {activeEventId === event.id ? "Hide" : "Open"}
                                  </button>
                                </div>

                                {activeEventId === event.id && (
                                  <>
                                    {event.legacy_memory_id && (() => {
                                      const linkedMemory = timeline.find((memory) => memory.id === event.legacy_memory_id);
                                      if (!linkedMemory) {
                                        return null;
                                      }
                                      return (
                                        <MemoryCard
                                          key={`event-memory-${linkedMemory.id}`}
                                          memory={linkedMemory}
                                          linkedQuestions={questions.filter((q) => q.source_memory_id === linkedMemory.id)}
                                          peopleOptions={peopleDirectory}
                                          formatBytes={formatBytes}
                                          resolveApiUrl={resolveApiUrl}
                                          onResearch={researchMemory}
                                          onAcceptSuggestion={acceptResearchSuggestion}
                                          onDismissSuggestion={dismissResearchSuggestion}
                                          onReanalyze={reanalyzeMemory}
                                          onDelete={deleteMemory}
                                          onAssignRecorder={assignRecorder}
                                          isBusy={isLoading || memoryActionId === linkedMemory.id || isRecording}
                                          hideHeader
                                        />
                                      );
                                    })()}
                                    {(questionsByEventId.get(event.id)?.length ?? 0) > 0 && (
                                      <div className="inlineQuestionList">
                                        <p className="inlineQuestionListLabel">Open questions for this event</p>
                                        {questionsByEventId.get(event.id)!.map(({ question, sourceMemory }) => (
                                          <article key={question.id} className="questionCard inlineQuestionCard">
                                            <p className="questionText">{question.text}</p>
                                            {sourceMemory && (
                                              <p className="questionSource">From: <em>{sourceMemory.event_description}</em></p>
                                            )}
                                            <div className="questionActions">
                                              <button
                                                className="primary"
                                                type="button"
                                                onClick={() => { setActiveQuestion(question); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                                                disabled={isRecording || isLoading}
                                              >
                                                Answer this
                                              </button>
                                              <button
                                                className="ghost"
                                                type="button"
                                                onClick={() => dismissQuestion(question.id)}
                                                disabled={isRecording || isLoading}
                                              >
                                                Remove
                                              </button>
                                            </div>
                                          </article>
                                        ))}
                                      </div>
                                    )}
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
                                  </>
                                )}
                              </article>
                            ))}
                          </div>
                        </>
                      )}
                    </article>
                  );
                })}
              </div>

              <article className="memory" style={{ marginTop: "0.75rem" }}>
                <h3>Unassigned Events</h3>
                <p className="meta">Events with no period assignment appear here so they never disappear from view.</p>
                <div className="lifeEventList">
                  {unassignedEvents.length === 0 && <p className="meta">No unassigned events.</p>}
                  {unassignedEvents.map((event) => (
                    <article key={event.id} className="memory">
                      <div className="periodSummaryRow">
                        <div>
                          <p style={{ margin: 0, fontWeight: 700 }}>{event.title}</p>
                          <p className="meta">Date: {event.event_date_text || "unknown"} | Linked assets: {event.linked_asset_count}{(questionsByEventId.get(event.id)?.length ?? 0) > 0 && ` | Questions: ${questionsByEventId.get(event.id)!.length}`}</p>
                        </div>
                        <button
                          className="secondary"
                          type="button"
                          onClick={async () => {
                            if (activeEventId === event.id) {
                              setActiveEventId(null);
                              setActiveEventAssets([]);
                              return;
                            }
                            setActiveEventId(event.id);
                            await loadAssetsForEvent(event.id);
                          }}
                        >
                          {activeEventId === event.id ? "Hide" : "Open"}
                        </button>
                      </div>

                      {activeEventId === event.id && (
                        <>
                          {event.legacy_memory_id && (() => {
                            const linkedMemory = timeline.find((memory) => memory.id === event.legacy_memory_id);
                            if (!linkedMemory) {
                              return null;
                            }
                            return (
                              <MemoryCard
                                key={`event-memory-${linkedMemory.id}`}
                                memory={linkedMemory}
                                linkedQuestions={questions.filter((q) => q.source_memory_id === linkedMemory.id)}
                                peopleOptions={peopleDirectory}
                                formatBytes={formatBytes}
                                resolveApiUrl={resolveApiUrl}
                                onResearch={researchMemory}
                                onAcceptSuggestion={acceptResearchSuggestion}
                                onDismissSuggestion={dismissResearchSuggestion}
                                onReanalyze={reanalyzeMemory}
                                onDelete={deleteMemory}
                                onAssignRecorder={assignRecorder}
                                isBusy={isLoading || memoryActionId === linkedMemory.id || isRecording}
                                hideHeader
                              />
                            );
                          })()}
                          {(questionsByEventId.get(event.id)?.length ?? 0) > 0 && (
                            <div className="inlineQuestionList">
                              <p className="inlineQuestionListLabel">Open questions for this event</p>
                              {questionsByEventId.get(event.id)!.map(({ question, sourceMemory }) => (
                                <article key={question.id} className="questionCard inlineQuestionCard">
                                  <p className="questionText">{question.text}</p>
                                  {sourceMemory && (
                                    <p className="questionSource">From: <em>{sourceMemory.event_description}</em></p>
                                  )}
                                  <div className="questionActions">
                                    <button
                                      className="primary"
                                      type="button"
                                      onClick={() => { setActiveQuestion(question); window.scrollTo({ top: 0, behavior: "smooth" }); }}
                                      disabled={isRecording || isLoading}
                                    >
                                      Answer this
                                    </button>
                                    <button
                                      className="ghost"
                                      type="button"
                                      onClick={() => dismissQuestion(question.id)}
                                      disabled={isRecording || isLoading}
                                    >
                                      Remove
                                    </button>
                                  </div>
                                </article>
                              ))}
                            </div>
                          )}
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
                              {lifeEvents.filter((candidate) => candidate.id !== event.id).map((candidate) => (
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
                        </>
                      )}
                    </article>
                  ))}
                </div>
              </article>

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
              {questionsWithNoContext.length > 0 && (
                <div className="questionsSection">
                  <p className="inlineQuestionListLabel" style={{ marginBottom: "0.5rem" }}>General open questions</p>
                  {questionsWithNoContext.map(({ question }) => (
                    <article key={question.id} className="questionCard">
                      <p className="questionText">{question.text}</p>
                      <div className="questionActions">
                        <button
                          className="primary"
                          type="button"
                          onClick={() => {
                            setActiveQuestion(question);
                            window.scrollTo({ top: 0, behavior: "smooth" });
                          }}
                          disabled={isRecording || isLoading}
                        >
                          Answer this
                        </button>
                        <button
                          className="ghost"
                          type="button"
                          onClick={() => dismissQuestion(question.id)}
                          disabled={isRecording || isLoading}
                        >
                          Remove
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
              {timelineStandaloneMemories.map((memory) => (
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
              {timeline.length > 0 && timelineStandaloneMemories.length === 0 && (
                <p className="meta">All captured memories are organized in Life Periods above.</p>
              )}
            </section>
          </>
      </div>

      {isCaptureDrawerOpen && (
        <button
          type="button"
          className="captureBackdrop"
          aria-label="Close new memory panel"
          onClick={() => setIsCaptureDrawerOpen(false)}
        />
      )}

      <aside className={`captureSidebar ${isCaptureDrawerOpen ? "isOpen" : ""}`}>
        <div className="captureSidebarHeader">
          <div>
            <h2>New Memory</h2>
          </div>
          <button
            type="button"
            className="ghost captureClose"
            onClick={() => setIsCaptureDrawerOpen(false)}
          >
            Close
          </button>
        </div>

        <div className="captureBlock">
          <h3 className="captureBlockTitle">Record Audio</h3>
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
        </div>

        <div className="captureBlock">
          <h3 className="captureBlockTitle">Upload a Document</h3>
          <p className="meta">Upload a PDF, image, or text file, or paste a screen clipping. Gemini will analyze it and save it as a memory entry.</p>
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
            <p className="meta">Click this area and press Ctrl+V, or drag and drop a PDF, image, or text file here.</p>
          </div>
          {(isUploadingDocument || isReadingClipboard) && <p className="status">Analyzing document with Gemini...</p>}
          {documentUploadError && <p className="status" style={{ color: "var(--error, #c00)" }}>{documentUploadError}</p>}
        </div>

        {pendingRecording && (
          <div className="captureBlock">
            <h3 className="captureBlockTitle">Latest Recording</h3>
            <p className="meta">
              Status: <span className="badge">{pendingRecording.status}</span>
            </p>
            <p className="meta">File size: {formatBytes(pendingRecording.sizeBytes)}</p>
            <audio controls preload="metadata" src={pendingRecording.audioUrl} style={{ width: "100%" }} />
            {pendingRecording.sizeBytes === 0 && (
              <p className="meta">This recording is empty (0 B), which explains silent playback.</p>
            )}
            {pendingRecording.error && <p className="meta">{pendingRecording.error}</p>}
          </div>
        )}
      </aside>
    </main>
  );
}
