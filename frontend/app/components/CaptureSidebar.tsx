import { useState, type ClipboardEventHandler, type DragEventHandler, type RefObject } from "react";
import type { Question } from "../types";

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

type CaptureSidebarProps = {
  isCaptureDrawerOpen: boolean;
  setIsCaptureDrawerOpen: (value: boolean) => void;
  selectedDeviceId: string;
  setSelectedDeviceId: (value: string) => void;
  audioDevices: AudioInputDevice[];
  audioLevel: number;
  isRecording: boolean;
  isLoading: boolean;
  activeQuestion: Question | null;
  setActiveQuestion: (value: Question | null) => void;
  status: string;
  startRecording: () => void;
  stopRecording: () => void;
  cancelRecording: () => void;
  documentFileInputRef: RefObject<HTMLInputElement>;
  isUploadingDocument: boolean;
  isReadingClipboard: boolean;
  isDragOverDocumentTarget: boolean;
  documentUploadError: string | null;
  uploadDocument: (file: File) => void;
  pasteImageFromClipboard: () => void;
  onDocumentPasteZonePaste: ClipboardEventHandler<HTMLDivElement>;
  onDocumentDragEnter: DragEventHandler<HTMLDivElement>;
  onDocumentDragOver: DragEventHandler<HTMLDivElement>;
  onDocumentDragLeave: DragEventHandler<HTMLDivElement>;
  onDocumentDrop: DragEventHandler<HTMLDivElement>;
  pendingRecording: PendingRecording | null;
  formatBytes: (bytes: number) => string;
  audioDeviceStorageKey: string;
};

export function CaptureSidebar({
  isCaptureDrawerOpen,
  setIsCaptureDrawerOpen,
  selectedDeviceId,
  setSelectedDeviceId,
  audioDevices,
  audioLevel,
  isRecording,
  isLoading,
  activeQuestion,
  setActiveQuestion,
  status,
  startRecording,
  stopRecording,
  cancelRecording,
  documentFileInputRef,
  isUploadingDocument,
  isReadingClipboard,
  isDragOverDocumentTarget,
  documentUploadError,
  uploadDocument,
  pasteImageFromClipboard,
  onDocumentPasteZonePaste,
  onDocumentDragEnter,
  onDocumentDragOver,
  onDocumentDragLeave,
  onDocumentDrop,
  pendingRecording,
  formatBytes,
  audioDeviceStorageKey,
}: CaptureSidebarProps) {
  const [showAdvancedAudio, setShowAdvancedAudio] = useState(false);

  return (
    <>
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
          {/* Keep device controls optional so the default path stays focused on one-tap capture. */}
          <button
            className="ghost advancedAudioToggle"
            type="button"
            onClick={() => setShowAdvancedAudio((current) => !current)}
            aria-expanded={showAdvancedAudio}
            aria-controls="quick-memory-audio-settings"
            disabled={isRecording || isLoading}
          >
            {showAdvancedAudio ? "Hide Advanced Audio" : "Advanced Audio"}
          </button>

          {showAdvancedAudio && (
            <div className="inputSection" id="quick-memory-audio-settings">
              <label className="meta" htmlFor="mic-select">Input device</label>
              <select
                id="mic-select"
                className="micSelect"
                value={selectedDeviceId}
                onChange={(event) => {
                  const nextDeviceId = event.target.value;
                  setSelectedDeviceId(nextDeviceId);
                  if (nextDeviceId) {
                    localStorage.setItem(audioDeviceStorageKey, nextDeviceId);
                  } else {
                    localStorage.removeItem(audioDeviceStorageKey);
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
          )}

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
          <p className="meta">Upload a PDF, image, or text file, or paste a screen clipping. It will be saved as an asset in the unlinked inbox.</p>
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
          {(isUploadingDocument || isReadingClipboard) && <p className="status">Uploading file...</p>}
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
    </>
  );
}
