"use client";

import { useEffect, useRef, useState } from "react";
import { DirectoryManager } from "./components/DirectoryManager";
import { MemoryCard } from "./components/MemoryCard";
import { DirectoryEntry, MemoryEntry, Question, AppSettings } from "./types";

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
  const [documentUploadError, setDocumentUploadError] = useState<string | null>(null);
  const documentFileInputRef = useRef<HTMLInputElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const currentPreviewAudioUrlRef = useRef<string | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const levelAnimationRef = useRef<number | null>(null);

  async function loadTimeline() {
    try {
      const [memoriesRes, questionsRes, peopleRes, placesRes, settingsRes] = await Promise.all([
        fetch(`${API_BASE}/api/memories`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/questions`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/people`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/places`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/settings`, { cache: "no-store" }),
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
    } catch (error) {
      setStatus("Could not load timeline from API.");
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
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }

    streamRef.current?.getTracks().forEach((track) => track.stop());
    stopAudioLevelMonitoring();
    setIsRecording(false);
    setStatus("Finalizing audio clip...");
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
        </div>
        <p className="status">{status}</p>
      </section>

      <section className="panel">
        <h2>Upload a Document</h2>
        <p className="meta">Upload a PDF, image, or text file — Gemini will produce a factual document analysis and save it as a memory entry.</p>
        <div className="controls">
          <input
            ref={documentFileInputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.txt"
            disabled={isUploadingDocument || isRecording || isLoading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                uploadDocument(file);
              }
            }}
            style={{ flex: 1 }}
          />
        </div>
        {isUploadingDocument && <p className="status">Analyzing document with Gemini...</p>}
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
