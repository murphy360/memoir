"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CaptureSidebar } from "./components/CaptureSidebar";
import { DirectorySidebar } from "./components/DirectorySidebar";
import { EventCard } from "./components/EventCard";
import { LifePeriodCard } from "./components/LifePeriodCard";
import { MemoryCard } from "./components/MemoryCard";
import { PeriodComposer } from "./components/PeriodComposer";
import { UnlinkedAssetsInbox } from "./components/UnlinkedAssetsInbox";
import { AssetEntry, EventFaceEntry, LifeEvent, MemoryEntry, Question, LifePeriodAnalysis } from "./types";
import {
  type TimelineBundle,
  analyzeLifePeriod,
  applyResearchSuggestionById,
  answerQuestionWithMemory,
  assignRecorderPerson,
  createDirectoryEntry as createDirectoryEntryRequest,
  createEvent,
  createMemoryFromAudioBlob,
  createPeriod,
  deleteAsset as deleteAssetById,
  deleteDirectoryEntry as deleteDirectoryEntryRequest,
  deleteEventById,
  deleteMemoryById,
  deletePeriodById,
  dismissQuestionById,
  dismissResearchSuggestionById,
  assignFacePerson,
  deleteFace,
  fetchEventAssets,
  fetchEventFaces,
  linkAssetToEvent,
  mergeEventInto,
  mergePeopleEntries,
  mergePeriodInto,
  reanalyzeMemoryById,
  removePersonAlias as removePersonAliasRequest,
  renameDirectoryEntry as renameDirectoryEntryRequest,
  renamePeriodTitle,
  updatePeriodDates,
  renameEventTitle,
  resolveApiUrl,
  saveMainCharacterName as saveMainCharacterNameRequest,
  splitPersonEntry as splitPersonEntryRequest,
  addPersonAlias as addPersonAliasRequest,
  updateEventById,
  updateMemoryTitle as updateMemoryTitleById,
  updateAssetNotes as updateAssetNotesById,
  updateAssetTitle as updateAssetTitleById,
  processEventPhotoAssets,
  uploadAsset,
} from "./lib/memoirApi";
import {
  AUDIO_DEVICE_STORAGE_KEY,
  displayPeriodSummary,
  formatBytes,
} from "./lib/memoirUi";
import { useTimelineData } from "./hooks/useTimelineData";
import { useEventActions } from "./hooks/useEventActions";
import { useDocumentIntake } from "./hooks/useDocumentIntake";
import { useRecordingController } from "./hooks/useRecordingController";
import {
  PeriodSortMode,
  UNASSIGNED_PERIOD_VALUE,
  compareDateStringsDesc,
  parsePeriodYearHint,
} from "./lib/homePageHelpers";

type PendingRecording = {
  id: string;
  audioUrl: string;
  sizeBytes: number;
  status: "recorded" | "processing" | "saved" | "failed";
  error?: string;
};

type EventDocumentUploadProgressItem = {
  fileName: string;
  status: "uploading" | "saved" | "failed";
  error?: string;
};

export default function HomePage() {
  const [isDirectoryDrawerOpen, setIsDirectoryDrawerOpen] = useState(false);
  const [isCaptureDrawerOpen, setIsCaptureDrawerOpen] = useState(false);
  const [activeDirectoryTab, setActiveDirectoryTab] = useState<"people" | "places">("people");
  const [directorySearch, setDirectorySearch] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [status, setStatus] = useState("Ready to record a memory.");
  const {
    timeline,
    lifePeriods,
    lifeEvents,
    unlinkedAssets,
    setUnlinkedAssets,
    questions,
    setQuestions,
    peopleDirectory,
    placesDirectory,
    mainCharacterName,
    setMainCharacterName,
    loadTimeline,
  } = useTimelineData({ setStatus });
  const [activeEventId, setActiveEventId] = useState<number | null>(null);
  const [activeEventAssets, setActiveEventAssets] = useState<AssetEntry[]>([]);
  const [activeEventFaces, setActiveEventFaces] = useState<EventFaceEntry[]>([]);
  const [assigningFaceId, setAssigningFaceId] = useState<number | null>(null);
  const [isSavingLifeStructure, setIsSavingLifeStructure] = useState(false);
  const [isUploadingAsset, setIsUploadingAsset] = useState(false);
  const [assetLinkTargets, setAssetLinkTargets] = useState<Record<number, string>>({});
  const [eventMergeTargets, setEventMergeTargets] = useState<Record<number, string>>({});
  const [eventMoveTargets, setEventMoveTargets] = useState<Record<number, string>>({});
  const [newPeriodTitle, setNewPeriodTitle] = useState("");
  const [newPeriodStart, setNewPeriodStart] = useState("");
  const [newPeriodEnd, setNewPeriodEnd] = useState("");
  const [newPeriodSummary, setNewPeriodSummary] = useState("");
  const [newEventTitle, setNewEventTitle] = useState("");
  const [newEventDateText, setNewEventDateText] = useState("");
  const [newEventDescription, setNewEventDescription] = useState("");
  const [newEventPeriodId, setNewEventPeriodId] = useState("");
  const [editingAssetTitleId, setEditingAssetTitleId] = useState<number | null>(null);
  const [editingAssetTitleValue, setEditingAssetTitleValue] = useState("");
  const [assetTitleSavingId, setAssetTitleSavingId] = useState<number | null>(null);
  const [processingEventPhotosId, setProcessingEventPhotosId] = useState<number | null>(null);
  const [editingAssetNotesId, setEditingAssetNotesId] = useState<number | null>(null);
  const [editingAssetNotesValue, setEditingAssetNotesValue] = useState("");
  const [assetNotesSavingId, setAssetNotesSavingId] = useState<number | null>(null);
  const [pendingRecording, setPendingRecording] = useState<PendingRecording | null>(null);
  const [recordingForEventId, setRecordingForEventId] = useState<number | null>(null);
  const [eventRecordingPending, setEventRecordingPending] = useState<Record<number, PendingRecording>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [highlightedElementId, setHighlightedElementId] = useState<string | null>(null);
  const [memoryActionId, setMemoryActionId] = useState<number | null>(null);
  const [directoryBusyKey, setDirectoryBusyKey] = useState<string | null>(null);
  const [isPeriodComposerOpen, setIsPeriodComposerOpen] = useState(false);
  const [expandedPeriods, setExpandedPeriods] = useState<Record<number, boolean>>({});
  const [eventDraftsByPeriod, setEventDraftsByPeriod] = useState<
    Record<number, { title: string; dateText: string; description: string; location: string }>
  >({});
  const [periodAnalysisById, setPeriodAnalysisById] = useState<Record<number, LifePeriodAnalysis | null>>({});
  const [periodAnalysisBusyId, setPeriodAnalysisBusyId] = useState<number | null>(null);
  const [editingPeriodTitleId, setEditingPeriodTitleId] = useState<number | null>(null);
  const [editingPeriodTitleValue, setEditingPeriodTitleValue] = useState("");
  const [editingPeriodDatesId, setEditingPeriodDatesId] = useState<number | null>(null);
  const [editingPeriodStartValue, setEditingPeriodStartValue] = useState("");
  const [editingPeriodEndValue, setEditingPeriodEndValue] = useState("");
  const [editingEventTitleId, setEditingEventTitleId] = useState<number | null>(null);
  const [editingEventTitleValue, setEditingEventTitleValue] = useState("");
  const [editingEventDateId, setEditingEventDateId] = useState<number | null>(null);
  const [editingEventDateValue, setEditingEventDateValue] = useState("");
  const [editingEventLocationId, setEditingEventLocationId] = useState<number | null>(null);
  const [editingEventLocationValue, setEditingEventLocationValue] = useState("");
  const [editingMemoryTitleId, setEditingMemoryTitleId] = useState<number | null>(null);
  const [editingMemoryTitleValue, setEditingMemoryTitleValue] = useState("");
  const [memoryTitleSavingId, setMemoryTitleSavingId] = useState<number | null>(null);
  const [expandedMemoryRowIds, setExpandedMemoryRowIds] = useState<Set<number>>(new Set());
  const [expandedAssetRowIds, setExpandedAssetRowIds] = useState<Set<number>>(new Set());
  const [eventCapturePanelOpenIds, setEventCapturePanelOpenIds] = useState<Set<number>>(new Set());
  const [eventDocumentUploadingId, setEventDocumentUploadingId] = useState<number | null>(null);
  const [eventDocumentErrors, setEventDocumentErrors] = useState<Record<number, string | null>>({});
  const [eventDocumentUploadProgressByEventId, setEventDocumentUploadProgressByEventId] = useState<Record<number, EventDocumentUploadProgressItem[]>>({});
  const [mergingPeriodId, setMergingPeriodId] = useState<number | null>(null);
  const [periodSortMode, setPeriodSortMode] = useState<PeriodSortMode>("timeline-asc");

  const [activeQuestion, setActiveQuestion] = useState<Question | null>(null);

  const [showCharacterInput, setShowCharacterInput] = useState(false);
  const [characterInputValue, setCharacterInputValue] = useState("");
  const [isSavingCharacter, setIsSavingCharacter] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const [isUploadingDocument, setIsUploadingDocument] = useState(false);
  const documentFileInputRef = useRef<HTMLInputElement | null>(null);
  const eventAssetInputRef = useRef<HTMLInputElement | null>(null);
  const focusClearTimerRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const shouldDiscardRecordingRef = useRef(false);
  const currentPreviewAudioUrlRef = useRef<string | null>(null);

  const {
    audioDevices,
    selectedDeviceId,
    setSelectedDeviceId,
    audioLevel,
    refreshAudioDevices,
    startAudioLevelMonitoring,
    stopAudioLevelMonitoring,
  } = useRecordingController(setStatus);

  const eventCountByPeriod = useMemo(() => {
    const counts: Record<number, number> = {};
    for (const event of lifeEvents) {
      if (event.period_id === null) {
        continue;
      }
      counts[event.period_id] = (counts[event.period_id] ?? 0) + 1;
    }
    return counts;
  }, [lifeEvents]);

  const sortedLifePeriods = useMemo(() => {
    const periods = [...lifePeriods];
    periods.sort((left, right) => {
      const leftStartYear = parsePeriodYearHint(left.start_date_text);
      const rightStartYear = parsePeriodYearHint(right.start_date_text);
      const leftEndYear = parsePeriodYearHint(left.end_date_text);
      const rightEndYear = parsePeriodYearHint(right.end_date_text);
      const leftEventCount = eventCountByPeriod[left.id] ?? left.event_count ?? 0;
      const rightEventCount = eventCountByPeriod[right.id] ?? right.event_count ?? 0;

      if (periodSortMode === "timeline-asc" || periodSortMode === "timeline-desc") {
        if (leftStartYear === null && rightStartYear !== null) {
          return 1;
        }
        if (leftStartYear !== null && rightStartYear === null) {
          return -1;
        }
        if (leftStartYear !== null && rightStartYear !== null && leftStartYear !== rightStartYear) {
          return periodSortMode === "timeline-asc"
            ? leftStartYear - rightStartYear
            : rightStartYear - leftStartYear;
        }
        if (leftEndYear === null && rightEndYear !== null) {
          return 1;
        }
        if (leftEndYear !== null && rightEndYear === null) {
          return -1;
        }
        if (leftEndYear !== null && rightEndYear !== null && leftEndYear !== rightEndYear) {
          return periodSortMode === "timeline-asc"
            ? leftEndYear - rightEndYear
            : rightEndYear - leftEndYear;
        }
      }

      if (periodSortMode === "events-desc") {
        if (leftEventCount !== rightEventCount) {
          return rightEventCount - leftEventCount;
        }
      }

      if (periodSortMode === "updated-desc") {
        const updatedCompare = compareDateStringsDesc(left.updated_at, right.updated_at);
        if (updatedCompare !== 0) {
          return updatedCompare;
        }
      }

      if (periodSortMode === "title-asc") {
        const titleCompare = left.title.localeCompare(right.title, undefined, { sensitivity: "base" });
        if (titleCompare !== 0) {
          return titleCompare;
        }
      }

      const createdCompare = compareDateStringsDesc(left.created_at, right.created_at);
      if (createdCompare !== 0) {
        return createdCompare;
      }
      return left.title.localeCompare(right.title, undefined, { sensitivity: "base" });
    });
    return periods;
  }, [eventCountByPeriod, lifePeriods, periodSortMode]);

  function markAndScrollTo(elementId: string, delayMs = 120) {
    window.setTimeout(() => {
      const element = document.getElementById(elementId);
      if (!element) {
        return;
      }

      element.scrollIntoView({ behavior: "smooth", block: "center" });
      setHighlightedElementId(elementId);

      if (focusClearTimerRef.current !== null) {
        window.clearTimeout(focusClearTimerRef.current);
      }
      focusClearTimerRef.current = window.setTimeout(() => {
        setHighlightedElementId((current) => (current === elementId ? null : current));
      }, 3200);
    }, delayMs);
  }

  function focusEventInTimeline(eventId: number, periodId: number | null) {
    if (periodId !== null) {
      setExpandedPeriods((current) => ({ ...current, [periodId]: true }));
    }
    setActiveEventId(eventId);
    void loadAssetsForEvent(eventId);
    markAndScrollTo(`event-card-${eventId}`, periodId !== null ? 220 : 120);
  }

  function focusMemoryInTimeline(memoryId: number, data: TimelineBundle | null) {
    const linkedEvent = data?.events?.find((event) => event.linked_memory_ids.includes(memoryId)) || null;
    if (linkedEvent) {
      focusEventInTimeline(linkedEvent.id, linkedEvent.period_id);
      markAndScrollTo(`memory-card-${memoryId}`, 320);
      return;
    }

    markAndScrollTo(`memory-card-${memoryId}`, 160);
  }

  async function loadAssetsForEvent(eventId: number) {
    try {
      const [assets, faces] = await Promise.all([
        fetchEventAssets(eventId),
        fetchEventFaces(eventId),
      ]);
      setActiveEventAssets(assets);
      setActiveEventFaces(faces);
    } catch {
      setStatus("Could not load assets for the selected event.");
      setActiveEventAssets([]);
      setActiveEventFaces([]);
    }
  }

  async function assignFaceToPerson(faceId: number, personId: number | null, eventId: number) {
    setAssigningFaceId(faceId);
    setStatus(personId === null ? "Clearing face assignment..." : "Saving face assignment...");
    try {
      await assignFacePerson(faceId, personId);
      if (activeEventId === eventId) {
        await loadAssetsForEvent(eventId);
      }
      setStatus(personId === null ? "Face assignment cleared." : "Face assignment saved.");
    } catch {
      setStatus("Failed to update face assignment.");
    } finally {
      setAssigningFaceId(null);
    }
  }

  async function discardFace(faceId: number, eventId: number) {
    setStatus("Discarding face...");
    try {
      await deleteFace(faceId);
      if (activeEventId === eventId) {
        setActiveEventFaces((prev) => prev.filter((f) => f.id !== faceId));
      }
      setStatus("Face discarded.");
    } catch {
      setStatus("Failed to discard face.");
    }
  }

  const {
    eventActionId,
    summarizeEvent,
    deepResearchEvent,
    acceptEventResearchSuggestion,
    dismissEventResearchSuggestion,
  } = useEventActions({
    activeEventId,
    loadTimeline,
    loadAssetsForEvent,
    setStatus,
  });

  async function createLifePeriod() {
    if (!newPeriodTitle.trim()) {
      return;
    }
    setIsSavingLifeStructure(true);
    setStatus("Creating period...");
    try {
      const created = await createPeriod({
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
      setExpandedPeriods((current) => ({ ...current, [created.id]: true }));
      markAndScrollTo(`period-card-${created.id}`, 220);
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
    location?: string;
    periodId?: number | null;
    resetPeriodDraftId?: number;
  }) {
    const title = options?.title ?? newEventTitle;
    const periodId = options?.periodId ?? (newEventPeriodId ? Number(newEventPeriodId) : null);
    const eventDateText = options?.eventDateText ?? newEventDateText;
    const description = options?.description ?? newEventDescription;
    const location = options?.location ?? "";

    if (!title.trim()) {
      return;
    }
    setIsSavingLifeStructure(true);
    setStatus("Creating event...");
    try {
      const created = await createEvent({
        title: title.trim(),
        period_id: periodId,
        description: description.trim() || null,
        location: location.trim() || null,
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
            location: "",
          },
        }));
      }
      await loadTimeline();
      focusEventInTimeline(created.id, created.period_id);
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
    patch: Partial<{ title: string; dateText: string; description: string; location: string }>,
  ) {
    setEventDraftsByPeriod((current) => ({
      ...current,
      [periodId]: {
        title: current[periodId]?.title || "",
        dateText: current[periodId]?.dateText || "",
        description: current[periodId]?.description || "",
        location: current[periodId]?.location || "",
        ...patch,
      },
    }));
  }

  async function savePeriodDates(periodId: number) {
    setStatus("Saving period dates...");
    try {
      await updatePeriodDates(
        periodId,
        editingPeriodStartValue.trim() || null,
        editingPeriodEndValue.trim() || null,
      );
      setEditingPeriodDatesId(null);
      await loadTimeline();
      setStatus("Period dates updated.");
    } catch {
      setStatus("Failed to update period dates.");
    }
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

  async function renameEvent(eventId: number, newTitle: string) {
    const trimmed = newTitle.trim();
    if (!trimmed) return;
    setStatus("Saving event title...");
    try {
      await renameEventTitle(eventId, trimmed);
      setEditingEventTitleId(null);
      setEditingEventTitleValue("");
      await loadTimeline();
      setStatus("Event title updated.");
    } catch {
      setStatus("Failed to rename event.");
    }
  }

  async function saveEventDate(eventId: number, newDateText: string) {
    setStatus("Saving event date...");
    try {
      await updateEventById(eventId, { event_date_text: newDateText.trim() || null });
      setEditingEventDateId(null);
      setEditingEventDateValue("");
      await loadTimeline();
      setStatus("Event date updated.");
    } catch {
      setStatus("Failed to update event date.");
    }
  }

  async function saveEventLocation(eventId: number, newLocation: string) {
    setStatus("Saving event location...");
    try {
      await updateEventById(eventId, { location: newLocation.trim() || null });
      setEditingEventLocationId(null);
      setEditingEventLocationValue("");
      await loadTimeline();
      setStatus("Event location updated.");
    } catch {
      setStatus("Failed to update event location.");
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
      const uploaded = await uploadAsset(formData);

      if (eventAssetInputRef.current) {
        eventAssetInputRef.current.value = "";
      }
      await Promise.all([loadTimeline(), loadAssetsForEvent(activeEventId)]);
      markAndScrollTo(`asset-row-${uploaded.id}`, 220);
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
    if (!window.confirm("Remove this event from the timeline? Linked memories and assets will be kept and moved to inbox/unlinked state.")) {
      return;
    }

    setIsSavingLifeStructure(true);
    setStatus("Removing event...");
    try {
      await deleteEventById(eventId);

      if (activeEventId === eventId) {
        setActiveEventId(null);
        setActiveEventAssets([]);
        setActiveEventFaces([]);
      }
      await loadTimeline();
      setStatus("Event removed. Memories and assets were kept.");
    } catch {
      setStatus("Failed to remove event.");
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

  async function moveEventToPeriod(event: LifeEvent) {
    const selectedTarget = eventMoveTargets[event.id] || (event.period_id === null ? UNASSIGNED_PERIOD_VALUE : `${event.period_id}`);
    const nextPeriodId = selectedTarget === UNASSIGNED_PERIOD_VALUE ? null : Number(selectedTarget);
    if (nextPeriodId === event.period_id) {
      return;
    }

    setIsSavingLifeStructure(true);
    setStatus("Moving event to selected period...");
    try {
      await updateEventById(event.id, { period_id: nextPeriodId });
      setEventMoveTargets((current) => {
        const next = { ...current };
        delete next[event.id];
        return next;
      });
      await loadTimeline();
      focusEventInTimeline(event.id, nextPeriodId);
      setStatus("Event moved.");
    } catch {
      setStatus("Failed to move event.");
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
    setStatus("Deleting memory permanently...");
    try {
      await deleteMemoryById(memoryId);
      await loadTimeline();
      setStatus("Memory permanently deleted.");
    } catch {
      setStatus("Failed to delete memory.");
    } finally {
      setMemoryActionId(null);
    }
  }

  async function deleteAsset(assetId: number, eventId?: number) {
    if (!window.confirm("Delete this asset permanently? This cannot be undone.")) {
      return;
    }

    setStatus("Deleting asset...");
    try {
      await deleteAssetById(assetId);
      if (eventId !== undefined) {
        await loadAssetsForEvent(eventId);
      } else {
        setUnlinkedAssets((current) => current.filter((a) => a.id !== assetId));
      }
      setStatus("Asset deleted.");
    } catch {
      setStatus("Failed to delete asset.");
    }
  }

  async function saveAssetTitle(assetId: number, eventId?: number) {
    setAssetTitleSavingId(assetId);
    setStatus("Saving asset title...");
    try {
      await updateAssetTitleById(assetId, editingAssetTitleValue.trim() || null);
      setEditingAssetTitleId(null);
      setEditingAssetTitleValue("");
      if (eventId !== undefined) {
        await loadAssetsForEvent(eventId);
      }
      await loadTimeline();
      setStatus("Asset title updated.");
    } catch {
      setStatus("Failed to update asset title.");
    } finally {
      setAssetTitleSavingId(null);
    }
  }

  async function saveAssetNotes(assetId: number, eventId?: number) {
    setAssetNotesSavingId(assetId);
    setStatus("Saving asset notes...");
    try {
      await updateAssetNotesById(assetId, editingAssetNotesValue.trim() || null);
      setEditingAssetNotesId(null);
      setEditingAssetNotesValue("");
      if (eventId !== undefined) {
        await loadAssetsForEvent(eventId);
      }
      await loadTimeline();
      setStatus("Asset notes updated.");
    } catch {
      setStatus("Failed to update asset notes.");
    } finally {
      setAssetNotesSavingId(null);
    }
  }

  async function processPhotosForEvent(eventId: number) {
    setProcessingEventPhotosId(eventId);
    setStatus("Reprocessing event photos...");
    try {
      const result = await processEventPhotoAssets(eventId, true);
      await loadTimeline();
      if (activeEventId === eventId) {
        await loadAssetsForEvent(eventId);
      }
      if (result.photos_processed > 0) {
        setStatus(`Reprocessed ${result.photos_processed} photo${result.photos_processed === 1 ? "" : "s"} for this event.`);
      } else {
        setStatus("No photo files were available to reprocess for this event.");
      }
    } catch {
      setStatus("Failed to process event photos.");
    } finally {
      setProcessingEventPhotosId(null);
    }
  }

  async function saveMemoryTitle(memoryId: number, eventId?: number) {
    const nextTitle = editingMemoryTitleValue.trim();
    if (!nextTitle) {
      setStatus("Memory title cannot be empty.");
      return;
    }
    setMemoryTitleSavingId(memoryId);
    setStatus("Saving memory title...");
    try {
      await updateMemoryTitleById(memoryId, nextTitle);
      setEditingMemoryTitleId(null);
      setEditingMemoryTitleValue("");
      const data = await loadTimeline();
      focusMemoryInTimeline(memoryId, data);
      if (eventId !== undefined) {
        await loadAssetsForEvent(eventId);
      }
      setStatus("Memory title updated.");
    } catch {
      setStatus("Failed to update memory title.");
    } finally {
      setMemoryTitleSavingId(null);
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

  useEffect(() => {
    return () => {
      if (focusClearTimerRef.current !== null) {
        window.clearTimeout(focusClearTimerRef.current);
      }
      if (currentPreviewAudioUrlRef.current) {
        URL.revokeObjectURL(currentPreviewAudioUrlRef.current);
      }
      stopAudioLevelMonitoring();
    };
  }, []);

  async function startRecording(forEventId?: number, options?: { quickCapture?: boolean }) {
    try {
      shouldDiscardRecordingRef.current = false;
      const isQuickCapture = options?.quickCapture === true && forEventId === undefined;
      const audioConstraint = selectedDeviceId
        ? { deviceId: { exact: selectedDeviceId } }
        : true;
      const stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraint });
      streamRef.current = stream;
      chunksRef.current = [];
      startAudioLevelMonitoring(stream);

      await refreshAudioDevices();

      const targetEventId = forEventId ?? null;
      setRecordingForEventId(targetEventId);

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
          setRecordingForEventId(null);
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

        if (targetEventId !== null) {
          setEventRecordingPending((prev) => ({
            ...prev,
            [targetEventId]: {
              id: nextPendingId,
              audioUrl: nextAudioUrl,
              sizeBytes: blob.size,
              status: "recorded",
            },
          }));
        } else {
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
        }

        setStatus("Audio recorded. You can play it now while we process it.");
        await uploadRecording(blob, nextPendingId, targetEventId ?? undefined, isQuickCapture);
      };

      recorder.start();
      setIsRecording(true);
      setStatus("Recording in progress...");
    } catch (error) {
      setStatus("Microphone permission denied or unavailable.");
    }
  }

  async function startQuickMemoryCapture() {
    // Quick Memory is designed to start capture from a single home-screen tap.
    setIsCaptureDrawerOpen(true);
    if (isRecording || isLoading) {
      return;
    }
    await startRecording(undefined, { quickCapture: true });
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
    setRecordingForEventId(null);
    setStatus("Canceling recording...");
  }

  async function uploadRecording(
    blob: Blob,
    pendingId: string,
    eventId?: number,
    quickCapture = false,
  ) {
    setIsLoading(true);

    const updatePending = (updater: (prev: PendingRecording) => PendingRecording) => {
      if (eventId !== undefined) {
        setEventRecordingPending((prev) => {
          const current = prev[eventId];
          if (!current || current.id !== pendingId) return prev;
          return { ...prev, [eventId]: updater(current) };
        });
      } else {
        setPendingRecording((current) =>
          current && current.id === pendingId ? updater(current) : current,
        );
      }
    };

    updatePending((p) => ({ ...p, status: "processing", error: undefined }));

    try {
      const created: MemoryEntry = await createMemoryFromAudioBlob(blob, eventId, quickCapture);
      if (activeQuestion) {
        try {
          await answerQuestionWithMemory(activeQuestion.id, created.id);
        } catch {
          // ignore answer errors
        }
        setActiveQuestion(null);
      }
      const data = await loadTimeline();
      focusMemoryInTimeline(created.id, data);
      if (eventId !== undefined) {
        await loadAssetsForEvent(eventId);
      }
      setStatus("Memory saved and analyzed.");
      setRecordingForEventId(null);
      updatePending((p) => ({ ...p, status: "saved", error: undefined }));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to process recording.";
      setStatus(message);
      updatePending((p) => ({
        ...p,
        status: "failed",
        error: message,
      }));
    } finally {
      setIsLoading(false);
    }
  }

  async function uploadDocument(file: File) {
    setIsUploadingDocument(true);
    setDocumentUploadError(null);
    setStatus("Uploading file...");
    try {
      const formData = new FormData();
      formData.append("file", file, file.name);
      const kind = file.type.startsWith("image/") ? "photo" : "document";
      formData.append("kind", kind);
      const uploaded = await uploadAsset(formData);

      await loadTimeline();
      markAndScrollTo(`asset-row-${uploaded.id}`, 180);
      setStatus("File uploaded to unlinked assets inbox.");
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

  const {
    isReadingClipboard,
    isDragOverDocumentTarget,
    documentUploadError,
    setDocumentUploadError,
    pasteImageFromClipboard,
    onDocumentPasteZonePaste,
    onDocumentDragEnter,
    onDocumentDragOver,
    onDocumentDragLeave,
    onDocumentDrop,
  } = useDocumentIntake({
    isUploadingDocument,
    isRecording,
    isLoading,
    uploadDocument,
  });

  async function uploadDocumentsToEvent(files: File[], eventId: number) {
    if (files.length === 0) {
      return;
    }

    // Seed a per-file progress list so the event panel can show live status updates.
    const initialProgress: EventDocumentUploadProgressItem[] = files.map((file) => ({
      fileName: file.name || "unnamed file",
      status: "uploading",
    }));

    setEventDocumentUploadingId(eventId);
    setEventDocumentErrors((prev) => ({ ...prev, [eventId]: null }));
    setEventDocumentUploadProgressByEventId((prev) => ({ ...prev, [eventId]: initialProgress }));
    setStatus(files.length === 1 ? "Uploading file to event..." : `Uploading ${files.length} files to event...`);
    try {
      const uploadedAssetIds: number[] = [];
      const failedFileNames: string[] = [];

      for (const [index, file] of files.entries()) {
        try {
          const formData = new FormData();
          formData.append("file", file, file.name);
          const kind = file.type.startsWith("image/") ? "photo" : "document";
          formData.append("kind", kind);
          formData.append("event_id", String(eventId));
          const uploaded = await uploadAsset(formData);
          uploadedAssetIds.push(uploaded.id);
          setEventDocumentUploadProgressByEventId((prev) => ({
            ...prev,
            [eventId]: (prev[eventId] ?? []).map((item, itemIndex) => (
              itemIndex === index ? { ...item, status: "saved", error: undefined } : item
            )),
          }));
        } catch {
          failedFileNames.push(file.name || "unnamed file");
          setEventDocumentUploadProgressByEventId((prev) => ({
            ...prev,
            [eventId]: (prev[eventId] ?? []).map((item, itemIndex) => (
              itemIndex === index ? { ...item, status: "failed", error: "Upload failed" } : item
            )),
          }));
        }
      }

      if (uploadedAssetIds.length === 0) {
        setEventDocumentErrors((prev) => ({
          ...prev,
          [eventId]: files.length === 1
            ? "Document upload failed."
            : `All ${files.length} uploads failed.`,
        }));
        setStatus("Document upload failed.");
        return;
      }

      await Promise.all([loadTimeline(), loadAssetsForEvent(eventId)]);
      markAndScrollTo(`asset-row-${uploadedAssetIds[uploadedAssetIds.length - 1]}`, 220);

      if (failedFileNames.length === 0) {
        setStatus(uploadedAssetIds.length === 1
          ? "File uploaded and linked to event."
          : `${uploadedAssetIds.length} files uploaded and linked to event.`);
      } else {
        setEventDocumentErrors((prev) => ({
          ...prev,
          [eventId]: `${failedFileNames.length} file(s) failed to upload: ${failedFileNames.slice(0, 3).join(", ")}${failedFileNames.length > 3 ? ", ..." : ""}`,
        }));
        setStatus(`${uploadedAssetIds.length} uploaded, ${failedFileNames.length} failed.`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to process document.";
      setEventDocumentErrors((prev) => ({ ...prev, [eventId]: message }));
      setStatus("Document upload failed.");
    } finally {
      setEventDocumentUploadingId(null);
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
      .flatMap((event) => event.linked_memory_ids),
  );
  const questionsWithContext = questions.map((question) => {
    const sourceMemory = question.source_memory_id
      ? timeline.find((memory) => memory.id === question.source_memory_id) ?? null
      : null;
    const sourceEvent = sourceMemory
      ? lifeEvents.find((event) => event.linked_memory_ids.includes(sourceMemory.id)) ?? null
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

  function renderEventCard(event: LifeEvent, mergeCandidates: LifeEvent[]) {
    return (
      <EventCard
        key={event.id}
        event={event}
        mergeCandidates={mergeCandidates}
        isHighlighted={highlightedElementId === `event-card-${event.id}`}
        isOpen={activeEventId === event.id}
        onToggleOpen={async () => {
          if (activeEventId === event.id) {
            setActiveEventId(null);
            setActiveEventAssets([]);
            setActiveEventFaces([]);
            return;
          }
          setActiveEventId(event.id);
          await loadAssetsForEvent(event.id);
        }}
        isSavingLifeStructure={isSavingLifeStructure}
        isRecording={isRecording}
        isLoading={isLoading}
        deleteLifeEvent={deleteLifeEvent}
        editingEventTitleId={editingEventTitleId}
        setEditingEventTitleId={setEditingEventTitleId}
        editingEventTitleValue={editingEventTitleValue}
        setEditingEventTitleValue={setEditingEventTitleValue}
        renameEvent={renameEvent}
        editingEventDateId={editingEventDateId}
        setEditingEventDateId={setEditingEventDateId}
        editingEventDateValue={editingEventDateValue}
        setEditingEventDateValue={setEditingEventDateValue}
        saveEventDate={saveEventDate}
        editingEventLocationId={editingEventLocationId}
        setEditingEventLocationId={setEditingEventLocationId}
        editingEventLocationValue={editingEventLocationValue}
        setEditingEventLocationValue={setEditingEventLocationValue}
        saveEventLocation={saveEventLocation}
        eventMoveTargets={eventMoveTargets}
        setEventMoveTargets={setEventMoveTargets}
        moveEventToPeriod={moveEventToPeriod}
        sortedLifePeriods={sortedLifePeriods}
        eventMergeTargets={eventMergeTargets}
        setEventMergeTargets={setEventMergeTargets}
        mergeLifeEvent={mergeLifeEvent}
        eventActionId={eventActionId}
        summarizeEvent={summarizeEvent}
        deepResearchEvent={deepResearchEvent}
        processingEventPhotosId={processingEventPhotosId}
        processEventPhotos={processPhotosForEvent}
        acceptEventResearchSuggestion={acceptEventResearchSuggestion}
        dismissEventResearchSuggestion={dismissEventResearchSuggestion}
        questionsForEvent={questionsByEventId.get(event.id) ?? []}
        setActiveQuestion={setActiveQuestion}
        dismissQuestion={dismissQuestion}
        eventCapturePanelOpenIds={eventCapturePanelOpenIds}
        setEventCapturePanelOpenIds={setEventCapturePanelOpenIds}
        recordingForEventId={recordingForEventId}
        audioDevices={audioDevices}
        selectedDeviceId={selectedDeviceId}
        setSelectedDeviceId={setSelectedDeviceId}
        audioLevel={audioLevel}
        startRecording={startRecording}
        stopRecording={stopRecording}
        cancelRecording={cancelRecording}
        eventRecordingPending={eventRecordingPending}
        eventDocumentUploadingId={eventDocumentUploadingId}
        eventDocumentErrors={eventDocumentErrors}
        eventDocumentUploadProgressByEventId={eventDocumentUploadProgressByEventId}
        uploadDocumentsToEvent={uploadDocumentsToEvent}
        eventAssetInputRef={eventAssetInputRef}
        isUploadingAsset={isUploadingAsset}
        uploadAssetToActiveEvent={uploadAssetToActiveEvent}
        activeEventAssets={activeEventAssets}
        eventFaces={activeEventFaces}
        highlightedElementId={highlightedElementId}
        expandedAssetRowIds={expandedAssetRowIds}
        setExpandedAssetRowIds={setExpandedAssetRowIds}
        editingAssetTitleId={editingAssetTitleId}
        setEditingAssetTitleId={setEditingAssetTitleId}
        editingAssetTitleValue={editingAssetTitleValue}
        setEditingAssetTitleValue={setEditingAssetTitleValue}
        assetTitleSavingId={assetTitleSavingId}
        saveAssetTitle={saveAssetTitle}
        editingAssetNotesId={editingAssetNotesId}
        setEditingAssetNotesId={setEditingAssetNotesId}
        editingAssetNotesValue={editingAssetNotesValue}
        setEditingAssetNotesValue={setEditingAssetNotesValue}
        assetNotesSavingId={assetNotesSavingId}
        saveAssetNotes={saveAssetNotes}
        resolveApiUrl={resolveApiUrl}
        formatBytes={formatBytes}
        deleteAsset={deleteAsset}
        assignFaceToPerson={assignFaceToPerson}
        assigningFaceId={assigningFaceId}
        timeline={timeline}
          discardFace={discardFace}
        editingMemoryTitleId={editingMemoryTitleId}
        setEditingMemoryTitleId={setEditingMemoryTitleId}
        editingMemoryTitleValue={editingMemoryTitleValue}
        setEditingMemoryTitleValue={setEditingMemoryTitleValue}
        memoryTitleSavingId={memoryTitleSavingId}
        saveMemoryTitle={saveMemoryTitle}
        expandedMemoryRowIds={expandedMemoryRowIds}
        setExpandedMemoryRowIds={setExpandedMemoryRowIds}
        questions={questions}
        peopleDirectory={peopleDirectory}
        acceptResearchSuggestion={acceptResearchSuggestion}
        dismissResearchSuggestion={dismissResearchSuggestion}
        reanalyzeMemory={reanalyzeMemory}
        deleteMemory={deleteMemory}
        assignRecorder={assignRecorder}
        memoryActionId={memoryActionId}
      />
    );
  }

  return (
    <main className="appShell">
      <DirectorySidebar
        isDirectoryDrawerOpen={isDirectoryDrawerOpen}
        setIsDirectoryDrawerOpen={setIsDirectoryDrawerOpen}
        activeDirectoryTab={activeDirectoryTab}
        setActiveDirectoryTab={setActiveDirectoryTab}
        directorySearch={directorySearch}
        setDirectorySearch={setDirectorySearch}
        activeDirectoryCount={activeDirectoryCount}
        activeDirectoryTotal={activeDirectoryTotal}
        normalizedDirectorySearch={normalizedDirectorySearch}
        filteredPeopleDirectory={filteredPeopleDirectory}
        filteredPlacesDirectory={filteredPlacesDirectory}
        isBusy={directoryBusyKey !== null || isLoading || isRecording}
        onCreateDirectoryEntry={createDirectoryEntry}
        onRenameDirectoryEntry={renameDirectoryEntry}
        onDeleteDirectoryEntry={deleteDirectoryEntry}
        onMergePersonEntry={mergePersonEntry}
        onSplitPersonEntry={splitPersonEntry}
        onAddPersonAlias={addPersonAlias}
        onRemovePersonAlias={removePersonAlias}
        resolveApiUrl={resolveApiUrl}
      />

      <div className="workspaceColumn">
        <section className="hero">
          <div className="heroRow">
            <h1>{mainCharacterName ? `${mainCharacterName}'s Memoir` : "Memoir MVP"}</h1>
            <div className="heroActions">
              <button
                type="button"
                className="primary captureToggle"
                onClick={() => void startQuickMemoryCapture()}
                disabled={isRecording || isLoading}
              >
                Quick Memory
              </button>
              <button
                type="button"
                className="secondary captureToggle"
                onClick={() => setIsCaptureDrawerOpen(true)}
              >
                + New Memory
              </button>
            </div>
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
                <div className="controls" style={{ justifyContent: "flex-end", marginBottom: 0 }}>
                  <label className="meta" htmlFor="period-sort-mode" style={{ alignSelf: "center" }}>
                    Sort
                  </label>
                  <select
                    id="period-sort-mode"
                    className="directoryInput"
                    value={periodSortMode}
                    onChange={(e) => setPeriodSortMode(e.target.value as PeriodSortMode)}
                    disabled={isSavingLifeStructure || isRecording || isLoading}
                    style={{ width: "min(18rem, 44vw)" }}
                  >
                    <option value="timeline-asc">Timeline: oldest first</option>
                    <option value="timeline-desc">Timeline: newest first</option>
                    <option value="events-desc">Most active first</option>
                    <option value="updated-desc">Recently updated</option>
                    <option value="title-asc">Title: A to Z</option>
                  </select>
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => setIsPeriodComposerOpen((current) => !current)}
                  >
                    {isPeriodComposerOpen ? "Hide period form" : "New period"}
                  </button>
                </div>
              </div>

              <PeriodComposer
                isOpen={isPeriodComposerOpen}
                newPeriodTitle={newPeriodTitle}
                setNewPeriodTitle={setNewPeriodTitle}
                newPeriodStart={newPeriodStart}
                setNewPeriodStart={setNewPeriodStart}
                newPeriodEnd={newPeriodEnd}
                setNewPeriodEnd={setNewPeriodEnd}
                newPeriodSummary={newPeriodSummary}
                setNewPeriodSummary={setNewPeriodSummary}
                isBusy={isSavingLifeStructure || isRecording || isLoading}
                createLifePeriod={createLifePeriod}
                onCreated={() => setIsPeriodComposerOpen(false)}
              />

              <div className="lifePeriodList">
                {lifePeriods.length === 0 && <p className="meta">No periods created yet.</p>}
                {sortedLifePeriods.map((period) => {
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
                    <LifePeriodCard
                      key={period.id}
                      period={period}
                      isHighlighted={highlightedElementId === `period-card-${period.id}`}
                    >
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
                              <span className="entityPill entityPillPeriod">Period</span>
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
                          {editingPeriodDatesId === period.id ? (
                            <div className="controls" style={{ marginBottom: "0.35rem", flexWrap: "wrap" }}>
                              <input
                                className="directoryInput"
                                type="text"
                                placeholder="Start (e.g. 1948)"
                                value={editingPeriodStartValue}
                                autoFocus
                                onChange={(e) => setEditingPeriodStartValue(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") savePeriodDates(period.id);
                                  if (e.key === "Escape") setEditingPeriodDatesId(null);
                                }}
                                style={{ width: "9rem" }}
                              />
                              <span className="meta" style={{ alignSelf: "center" }}>to</span>
                              <input
                                className="directoryInput"
                                type="text"
                                placeholder="End (e.g. 1960)"
                                value={editingPeriodEndValue}
                                onChange={(e) => setEditingPeriodEndValue(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") savePeriodDates(period.id);
                                  if (e.key === "Escape") setEditingPeriodDatesId(null);
                                }}
                                style={{ width: "9rem" }}
                              />
                              <button className="primary" type="button" onClick={() => savePeriodDates(period.id)}>Save</button>
                              <button className="secondary" type="button" onClick={() => setEditingPeriodDatesId(null)}>Cancel</button>
                            </div>
                          ) : (
                            <p className="meta">
                              Range: <span className="badge">{period.start_date_text || "unknown"}</span> to{" "}
                              <span className="badge">{period.end_date_text || "unknown"}</span>
                              <button
                                className="secondary"
                                type="button"
                                title="Edit dates"
                                style={{ marginLeft: "0.4rem", padding: "0.1rem 0.45rem", fontSize: "0.8rem" }}
                                onClick={() => {
                                  setEditingPeriodDatesId(period.id);
                                  setEditingPeriodStartValue(period.start_date_text ?? "");
                                  setEditingPeriodEndValue(period.end_date_text ?? "");
                                }}
                              >
                                ✏️
                              </button>
                            </p>
                          )}
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
                              {sortedLifePeriods
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
                              <input
                                className="directoryInput"
                                type="text"
                                placeholder="Location (optional)"
                                value={draft.location || ""}
                                onChange={(e) => updateEventDraftForPeriod(period.id, { location: e.target.value })}
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
                                    location: draft.location,
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
                            {eventsForPeriod.map((event) => renderEventCard(event, eventsForPeriod))}
                          </div>
                        </>
                      )}
                    </LifePeriodCard>
                  );
                })}
              </div>

              <article className="memory" style={{ marginTop: "0.75rem" }}>
                <h3>Unassigned Events</h3>
                <p className="meta">Events with no period assignment appear here so they never disappear from view.</p>
                <div className="lifeEventList">
                  {unassignedEvents.length === 0 && <p className="meta">No unassigned events.</p>}
                  {unassignedEvents.map((event) => renderEventCard(event, lifeEvents))}
                </div>
              </article>

              <UnlinkedAssetsInbox
                unlinkedAssets={unlinkedAssets}
                highlightedElementId={highlightedElementId}
                expandedAssetRowIds={expandedAssetRowIds}
                setExpandedAssetRowIds={setExpandedAssetRowIds}
                editingAssetTitleId={editingAssetTitleId}
                setEditingAssetTitleId={setEditingAssetTitleId}
                editingAssetTitleValue={editingAssetTitleValue}
                setEditingAssetTitleValue={setEditingAssetTitleValue}
                assetTitleSavingId={assetTitleSavingId}
                saveAssetTitle={saveAssetTitle}
                editingAssetNotesId={editingAssetNotesId}
                setEditingAssetNotesId={setEditingAssetNotesId}
                editingAssetNotesValue={editingAssetNotesValue}
                setEditingAssetNotesValue={setEditingAssetNotesValue}
                assetNotesSavingId={assetNotesSavingId}
                saveAssetNotes={saveAssetNotes}
                resolveApiUrl={resolveApiUrl}
                formatBytes={formatBytes}
                deleteAsset={deleteAsset}
                lifeEvents={lifeEvents}
                assetLinkTargets={assetLinkTargets}
                setAssetLinkTargets={setAssetLinkTargets}
                linkUnlinkedAssetToEvent={linkUnlinkedAssetToEvent}
                isSavingLifeStructure={isSavingLifeStructure}
              />
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
                  containerId={`memory-card-${memory.id}`}
                  isHighlighted={highlightedElementId === `memory-card-${memory.id}`}
                  memory={memory}
                  linkedQuestions={questions.filter((q) => q.source_memory_id === memory.id)}
                  peopleOptions={peopleDirectory}
                  formatBytes={formatBytes}
                  resolveApiUrl={resolveApiUrl}
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

      <CaptureSidebar
        isCaptureDrawerOpen={isCaptureDrawerOpen}
        setIsCaptureDrawerOpen={setIsCaptureDrawerOpen}
        selectedDeviceId={selectedDeviceId}
        setSelectedDeviceId={setSelectedDeviceId}
        audioDevices={audioDevices}
        audioLevel={audioLevel}
        isRecording={isRecording}
        isLoading={isLoading}
        activeQuestion={activeQuestion}
        setActiveQuestion={setActiveQuestion}
        status={status}
        startRecording={() => startRecording()}
        stopRecording={stopRecording}
        cancelRecording={cancelRecording}
        documentFileInputRef={documentFileInputRef}
        isUploadingDocument={isUploadingDocument}
        isReadingClipboard={isReadingClipboard}
        isDragOverDocumentTarget={isDragOverDocumentTarget}
        documentUploadError={documentUploadError}
        uploadDocument={uploadDocument}
        pasteImageFromClipboard={pasteImageFromClipboard}
        onDocumentPasteZonePaste={onDocumentPasteZonePaste}
        onDocumentDragEnter={onDocumentDragEnter}
        onDocumentDragOver={onDocumentDragOver}
        onDocumentDragLeave={onDocumentDragLeave}
        onDocumentDrop={onDocumentDrop}
        pendingRecording={pendingRecording}
        formatBytes={formatBytes}
        audioDeviceStorageKey={AUDIO_DEVICE_STORAGE_KEY}
      />
    </main>
  );
}
