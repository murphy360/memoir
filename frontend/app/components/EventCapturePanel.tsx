import type { RefObject } from "react";

const EVENT_AUDIO_STORAGE_KEY = "memoir.audioInputDeviceId";

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

type EventCapturePanelProps = {
  eventId: number;
  isRecording: boolean;
  isLoading: boolean;
  recordingForEventId: number | null;
  audioDevices: AudioInputDevice[];
  selectedDeviceId: string;
  setSelectedDeviceId: (value: string) => void;
  audioLevel: number;
  startRecording: (eventId: number) => void;
  stopRecording: () => void;
  cancelRecording: () => void;
  eventRecordingPending: Record<number, PendingRecording>;
  eventDocumentUploadingId: number | null;
  eventDocumentErrors: Record<number, string | null>;
  uploadDocumentToEvent: (file: File, eventId: number) => void;
  eventAssetInputRef: RefObject<HTMLInputElement>;
  isUploadingAsset: boolean;
  isSavingLifeStructure: boolean;
  uploadAssetToActiveEvent: (file: File) => void;
};

export function EventCapturePanel({
  eventId,
  isRecording,
  isLoading,
  recordingForEventId,
  audioDevices,
  selectedDeviceId,
  setSelectedDeviceId,
  audioLevel,
  startRecording,
  stopRecording,
  cancelRecording,
  eventRecordingPending,
  eventDocumentUploadingId,
  eventDocumentErrors,
  uploadDocumentToEvent,
  eventAssetInputRef,
  isUploadingAsset,
  isSavingLifeStructure,
  uploadAssetToActiveEvent,
}: EventCapturePanelProps) {
  return (
    <div className="eventCapturePanel">
      <div className="captureBlock">
        <h4 className="captureBlockTitle">Record Audio</h4>
        <div className="inputSection">
          <label className="meta" htmlFor={`event-mic-${eventId}`}>Input device</label>
          <select
            id={`event-mic-${eventId}`}
            className="micSelect"
            value={selectedDeviceId}
            onChange={(e) => {
              const nextDeviceId = e.target.value;
              setSelectedDeviceId(nextDeviceId);
              if (nextDeviceId) localStorage.setItem(EVENT_AUDIO_STORAGE_KEY, nextDeviceId);
              else localStorage.removeItem(EVENT_AUDIO_STORAGE_KEY);
            }}
            disabled={isRecording || isLoading || audioDevices.length === 0}
          >
            {audioDevices.length === 0 && <option value="">No microphones found</option>}
            {audioDevices.map((device) => (
              <option key={device.deviceId} value={device.deviceId}>{device.label}</option>
            ))}
          </select>
          <div className="levelWrap" aria-label="audio input level">
            <div className="levelTrack">
              <div className="levelFill" style={{ width: `${Math.round(audioLevel * 100)}%` }} />
            </div>
            <span className="meta levelText">Input level: {Math.round(audioLevel * 100)}%</span>
          </div>
        </div>
        {recordingForEventId === eventId ? (
          <>
            <p className="meta" style={{ marginBottom: "0.35rem" }}>Recording... <span className="badge">live</span></p>
            <div className="controls">
              <button className="secondary" type="button" onClick={stopRecording} disabled={!isRecording || isLoading}>Stop &amp; Process</button>
              <button className="ghost" type="button" onClick={cancelRecording} disabled={!isRecording || isLoading}>Cancel</button>
            </div>
          </>
        ) : (
          <div className="controls">
            <button className="primary" type="button" onClick={() => startRecording(eventId)} disabled={isRecording || isLoading || audioDevices.length === 0}>Start Recording</button>
          </div>
        )}
        {eventRecordingPending[eventId] && (
          <div className="pendingRecordingInline" style={{ marginTop: "0.5rem" }}>
            <audio controls preload="metadata" src={eventRecordingPending[eventId].audioUrl} style={{ flex: 1 }} />
            <span className="meta">
              {eventRecordingPending[eventId].status === "processing" && "Processing..."}
              {eventRecordingPending[eventId].status === "saved" && "Saved ✓"}
              {eventRecordingPending[eventId].status === "failed" && (eventRecordingPending[eventId].error ?? "Failed")}
            </span>
          </div>
        )}
      </div>
      <div className="captureBlock">
        <h4 className="captureBlockTitle">Upload a Document</h4>
        <p className="meta">Upload a PDF, image, or text file and link it directly to this event as an asset.</p>
        <div className="controls">
          <input
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.txt"
            disabled={eventDocumentUploadingId === eventId || isRecording || isLoading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) uploadDocumentToEvent(file, eventId);
              e.currentTarget.value = "";
            }}
            style={{ flex: 1 }}
          />
        </div>
        {eventDocumentUploadingId === eventId && <p className="status">Uploading...</p>}
        {eventDocumentErrors[eventId] && <p className="status" style={{ color: "var(--error, #c00)" }}>{eventDocumentErrors[eventId]}</p>}
      </div>
      <div className="captureBlock">
        <h4 className="captureBlockTitle">Upload Asset</h4>
        <p className="meta">Upload a photo, audio, or file directly as an asset without AI analysis.</p>
        <input
          ref={eventAssetInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.txt,.mp3,.wav,.m4a,.ogg,.webm,audio/*"
          disabled={isUploadingAsset || isSavingLifeStructure || isRecording || isLoading}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) uploadAssetToActiveEvent(file);
          }}
        />
      </div>
    </div>
  );
}
