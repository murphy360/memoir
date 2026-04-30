"use client";

import { useEffect, useRef, useState } from "react";

type MemoryEntry = {
  id: number;
  transcript: string;
  event_description: string;
  estimated_date_text: string | null;
  emotional_tone: string;
  follow_up_question: string;
  audio_size_bytes: number | null;
  audio_url: string | null;
  created_at: string;
};

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

type Question = {
  id: number;
  text: string;
  source_memory_id: number | null;
  status: string;
  created_at: string;
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

export default function HomePage() {
  const [isRecording, setIsRecording] = useState(false);
  const [status, setStatus] = useState("Ready to record a memory.");
  const [timeline, setTimeline] = useState<MemoryEntry[]>([]);
  const [pendingRecording, setPendingRecording] = useState<PendingRecording | null>(null);
  const [audioDevices, setAudioDevices] = useState<AudioInputDevice[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [audioLevel, setAudioLevel] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  const [questions, setQuestions] = useState<Question[]>([]);
  const [activeQuestion, setActiveQuestion] = useState<Question | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const currentPreviewAudioUrlRef = useRef<string | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const levelAnimationRef = useRef<number | null>(null);

  async function loadTimeline() {
    try {
      const [memoriesRes, questionsRes] = await Promise.all([
        fetch(`${API_BASE}/api/memories`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/questions`, { cache: "no-store" }),
      ]);
      if (!memoriesRes.ok) {
        throw new Error("Failed to load timeline");
      }
      const data: MemoryEntry[] = await memoriesRes.json();
      setTimeline(data);
      if (questionsRes.ok) {
        const questionsData: Question[] = await questionsRes.json();
        setQuestions(questionsData);
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

  return (
    <main>
      <section className="hero">
        <h1>Memoir MVP</h1>
        <p>Record a memory, extract a timeline clue, and get one follow-up question.</p>
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

      <section className="timeline">
        {questions.length > 0 && (
          <div className="questionsSection">
            {questions.map((q) => (
              <article key={q.id} className="questionCard">
                <p className="questionText">{q.text}</p>
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
                    Not now
                  </button>
                </div>
              </article>
            ))}
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
          <article key={memory.id} className="memory">
            <h3>{memory.event_description}</h3>
            <p className="meta">
              Estimated time: {memory.estimated_date_text || "Unknown"} | Tone: <span className="badge">{memory.emotional_tone}</span>
            </p>
            {memory.audio_size_bytes !== null && (
              <p className="meta">Stored audio size: {formatBytes(memory.audio_size_bytes)}</p>
            )}
            {memory.audio_url && (
              <audio controls preload="metadata" src={resolveApiUrl(memory.audio_url)} style={{ width: "100%" }} />
            )}
            <p>{memory.transcript}</p>
          </article>
        ))}
        {timeline.length === 0 && <p className="meta">No memories yet. Record your first one.</p>}
      </section>
    </main>
  );
}
