import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import {
  formatAssetCaptureDate,
  formatAssetGps,
  renderImageMetadataBadges,
} from "../lib/homePageHelpers";
import type { AssetEntry, EventFaceEntry } from "../types";

type EventAssetListProps = {
  assets: AssetEntry[];
  highlightedElementId: string | null;
  expandedAssetRowIds: Set<number>;
  setExpandedAssetRowIds: Dispatch<SetStateAction<Set<number>>>;
  editingAssetTitleId: number | null;
  setEditingAssetTitleId: (id: number | null) => void;
  editingAssetTitleValue: string;
  setEditingAssetTitleValue: (value: string) => void;
  assetTitleSavingId: number | null;
  saveAssetTitle: (assetId: number, eventId?: number) => Promise<void>;
  editingAssetNotesId: number | null;
  setEditingAssetNotesId: (id: number | null) => void;
  editingAssetNotesValue: string;
  setEditingAssetNotesValue: (value: string) => void;
  assetNotesSavingId: number | null;
  saveAssetNotes: (assetId: number, eventId?: number) => Promise<void>;
  resolveApiUrl: (path: string) => string;
  formatBytes: (bytes: number) => string;
  deleteAsset: (assetId: number, eventId?: number) => Promise<void>;
  eventId?: number;
  eventFaces?: EventFaceEntry[];
  processPhotoAsset?: (assetId: number, eventId: number) => Promise<void>;
  processingPhotoAssetId?: number | null;
  recordingForAssetId?: number | null;
  startRecordingForAsset?: (assetId: number, eventId: number) => Promise<void>;
  stopRecording?: () => void;
  cancelRecording?: () => void;
  assetRecordingPending?: Record<number, {
    id: string;
    audioUrl: string;
    sizeBytes: number;
    status: "recorded" | "processing" | "saved" | "failed";
    error?: string;
  }>;
  isRecording?: boolean;
  isLoading?: boolean;
  audioDevices?: Array<{ deviceId: string; label: string }>;
  showLinkControls?: boolean;
  lifeEvents?: Array<{ id: number; title: string }>;
  assetLinkTargets?: Record<number, string>;
  setAssetLinkTargets?: Dispatch<SetStateAction<Record<number, string>>>;
  linkUnlinkedAssetToEvent?: (assetId: number) => Promise<void>;
  isSavingLifeStructure?: boolean;
};

function isImageAsset(asset: AssetEntry): boolean {
  const contentType = (asset.content_type || "").toLowerCase();
  return asset.kind === "photo" || contentType.startsWith("image/");
}

function isAudioAsset(asset: AssetEntry): boolean {
  const contentType = (asset.content_type || "").toLowerCase();
  return asset.kind === "recording" || contentType.startsWith("audio/");
}

function isDocumentAsset(asset: AssetEntry): boolean {
  return asset.kind === "document";
}

function isPdfAsset(asset: AssetEntry): boolean {
  return (asset.content_type || "").toLowerCase().includes("pdf");
}

function fileExtension(name: string | null): string {
  const raw = (name || "").trim();
  if (!raw || !raw.includes(".")) {
    return "FILE";
  }
  const ext = raw.split(".").pop() || "FILE";
  return ext.slice(0, 5).toUpperCase();
}

export function EventAssetList({
  assets,
  highlightedElementId,
  expandedAssetRowIds,
  setExpandedAssetRowIds,
  editingAssetTitleId,
  setEditingAssetTitleId,
  editingAssetTitleValue,
  setEditingAssetTitleValue,
  assetTitleSavingId,
  saveAssetTitle,
  editingAssetNotesId,
  setEditingAssetNotesId,
  editingAssetNotesValue,
  setEditingAssetNotesValue,
  assetNotesSavingId,
  saveAssetNotes,
  resolveApiUrl,
  formatBytes,
  deleteAsset,
  eventId,
  eventFaces = [],
  processPhotoAsset,
  processingPhotoAssetId = null,
  recordingForAssetId = null,
  startRecordingForAsset,
  stopRecording,
  cancelRecording,
  assetRecordingPending = {},
  isRecording = false,
  isLoading = false,
  audioDevices = [],
  showLinkControls = false,
  lifeEvents = [],
  assetLinkTargets = {},
  setAssetLinkTargets,
  linkUnlinkedAssetToEvent,
  isSavingLifeStructure = false,
}: EventAssetListProps) {
  const [previewAssetId, setPreviewAssetId] = useState<number | null>(null);
  const [modalEditingTitleId, setModalEditingTitleId] = useState<number | null>(null);
  const [modalEditingTitleValue, setModalEditingTitleValue] = useState("");
  const [modalEditingNotesId, setModalEditingNotesId] = useState<number | null>(null);
  const [modalEditingNotesValue, setModalEditingNotesValue] = useState("");
  const [showFaceBoxesByAssetId, setShowFaceBoxesByAssetId] = useState<Record<number, boolean>>({});

  const galleryAssets = useMemo(
    () => assets.filter((asset) => isImageAsset(asset) || isAudioAsset(asset) || isDocumentAsset(asset)),
    [assets],
  );

  const previewAsset = useMemo(
    () => assets.find((asset) => asset.id === previewAssetId) || null,
    [assets, previewAssetId],
  );

  const previewAssetFaces = useMemo(() => {
    if (!previewAsset) {
      return [];
    }
    return eventFaces.filter((face) => face.asset_id === previewAsset.id);
  }, [eventFaces, previewAsset]);

  const showFaceBoxes = previewAsset ? Boolean(showFaceBoxesByAssetId[previewAsset.id]) : false;
  const hasPreviewGps = Boolean(
    previewAsset
    && previewAsset.gps_latitude !== null
    && previewAsset.gps_longitude !== null,
  );
  const previewPositionText = hasPreviewGps && previewAsset
    ? `${previewAsset.gps_latitude!.toFixed(6)}, ${previewAsset.gps_longitude!.toFixed(6)}`
    : "Unavailable";
  const previewMapUrl = hasPreviewGps && previewAsset
    ? `https://www.google.com/maps?q=${previewAsset.gps_latitude},${previewAsset.gps_longitude}`
    : null;

  const handleCloseModal = () => {
    setPreviewAssetId(null);
    setModalEditingTitleId(null);
    setModalEditingTitleValue("");
    setModalEditingNotesId(null);
    setModalEditingNotesValue("");
  };

  const canProcessPreviewPhoto = Boolean(
    previewAsset
    && isImageAsset(previewAsset)
    && processPhotoAsset
    && eventId !== undefined,
  );
  const canRecordPreviewPhoto = Boolean(
    previewAsset
    && isImageAsset(previewAsset)
    && startRecordingForAsset
    && eventId !== undefined,
  );
  const isRecordingThisAsset = Boolean(previewAsset && recordingForAssetId === previewAsset.id);
  const previewPendingRecording = previewAsset ? assetRecordingPending[previewAsset.id] : undefined;

  return (
    <>
    {galleryAssets.length > 0 && (
      <div className="assetGridGallery">
        {galleryAssets.map((asset) => (
          <button
            key={asset.id}
            className="assetGridTile"
            type="button"
            onClick={() => setPreviewAssetId(asset.id)}
            title={asset.title || asset.original_filename || `Asset ${asset.id}`}
          >
            {isImageAsset(asset) && (
              <img
                src={resolveApiUrl(`${asset.download_url}?download=false`)}
                alt={asset.title || asset.original_filename || `Asset ${asset.id}`}
              />
            )}
            {isAudioAsset(asset) && (
              <div className="assetAudioTile">🎵</div>
            )}
            {isDocumentAsset(asset) && (
              <div className="assetDocTile">{fileExtension(asset.original_filename)}</div>
            )}
          </button>
        ))}
      </div>
    )}
    {previewAsset && (
      <div className="assetPreviewOverlay" role="dialog" aria-modal="true" onClick={handleCloseModal}>
        <div className="assetPreviewModal" onClick={(e) => e.stopPropagation()}>
          <div className="assetPreviewHeader">
            {modalEditingTitleId === previewAsset.id ? (
              <div className="controls" style={{ display: "flex", gap: "0.5rem", flex: 1 }}>
                <input
                  className="directoryInput"
                  type="text"
                  value={modalEditingTitleValue}
                  autoFocus
                  onChange={(e) => setModalEditingTitleValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      void saveAssetTitle(previewAsset.id, eventId);
                      setModalEditingTitleId(null);
                    }
                    if (e.key === "Escape") {
                      setModalEditingTitleId(null);
                      setModalEditingTitleValue("");
                    }
                  }}
                />
                <button className="primary" type="button" onClick={() => { void saveAssetTitle(previewAsset.id, eventId); setModalEditingTitleId(null); }} disabled={assetTitleSavingId === previewAsset.id}>Save</button>
                <button className="secondary" type="button" onClick={() => { setModalEditingTitleId(null); setModalEditingTitleValue(""); }}>Cancel</button>
              </div>
            ) : (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flex: 1 }}>
                <h3>{previewAsset.title || previewAsset.original_filename || `Asset ${previewAsset.id}`}</h3>
                <button className="secondary" type="button" style={{ whiteSpace: "nowrap" }} onClick={() => { setModalEditingTitleId(previewAsset.id); setModalEditingTitleValue(previewAsset.title || ""); }}>Edit Title</button>
              </div>
            )}
            <button className="secondary" type="button" onClick={handleCloseModal} style={{ marginLeft: "0.5rem" }}>Close</button>
          </div>

          <p className="meta">
            {previewAsset.kind}{previewAsset.size_bytes ? ` · ${formatBytes(previewAsset.size_bytes)}` : ""}
          </p>

          {isImageAsset(previewAsset) && (
            <>
              {canProcessPreviewPhoto && (
                <div className="assetPreviewImageControls">
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => {
                      if (!processPhotoAsset || eventId === undefined) {
                        return;
                      }
                      void processPhotoAsset(previewAsset.id, eventId);
                    }}
                    disabled={processingPhotoAssetId === previewAsset.id}
                  >
                    {processingPhotoAssetId === previewAsset.id ? "Analyzing..." : "Analyze Photo"}
                  </button>
                  {previewAssetFaces.length > 0 && (
                    <button
                      className="secondary"
                      type="button"
                      onClick={() => setShowFaceBoxesByAssetId((current) => ({
                        ...current,
                        [previewAsset.id]: !current[previewAsset.id],
                      }))}
                    >
                      {showFaceBoxes ? "Hide Face Boxes" : `Show Face Boxes (${previewAssetFaces.length})`}
                    </button>
                  )}
                  {canRecordPreviewPhoto && !isRecordingThisAsset && (
                    <button
                      className="secondary"
                      type="button"
                      onClick={() => {
                        if (!previewAsset || !startRecordingForAsset || eventId === undefined) {
                          return;
                        }
                        void startRecordingForAsset(previewAsset.id, eventId);
                      }}
                      disabled={isRecording || isLoading || audioDevices.length === 0}
                    >
                      Record Voice Memory
                    </button>
                  )}
                  {canRecordPreviewPhoto && isRecordingThisAsset && (
                    <>
                      <button
                        className="secondary"
                        type="button"
                        onClick={stopRecording}
                        disabled={!isRecording || isLoading}
                      >
                        Stop &amp; Save
                      </button>
                      <button
                        className="ghost"
                        type="button"
                        onClick={cancelRecording}
                        disabled={!isRecording || isLoading}
                      >
                        Cancel
                      </button>
                    </>
                  )}
                </div>
              )}
              {previewPendingRecording && (
                <div className="pendingRecordingInline" style={{ marginTop: "0.6rem" }}>
                  <audio controls preload="metadata" src={previewPendingRecording.audioUrl} style={{ flex: 1 }} />
                  <span className="meta">
                    {previewPendingRecording.status === "processing" && "Processing..."}
                    {previewPendingRecording.status === "saved" && "Saved to photo ✓"}
                    {previewPendingRecording.status === "failed" && (previewPendingRecording.error ?? "Failed")}
                  </span>
                </div>
              )}
              <div className="assetPreviewImageWrap">
                <img
                  src={resolveApiUrl(`${previewAsset.download_url}?download=false`)}
                  alt={previewAsset.title || previewAsset.original_filename || `Asset ${previewAsset.id}`}
                  className="assetPreviewImage"
                />
                {showFaceBoxes && previewAssetFaces.map((face) => {
                  const left = Math.max(0, Math.min(100, face.bbox_x * 100));
                  const top = Math.max(0, Math.min(100, face.bbox_y * 100));
                  const width = Math.max(1, Math.min(100, face.bbox_w * 100));
                  const height = Math.max(1, Math.min(100, face.bbox_h * 100));
                  return (
                    <div
                      key={face.id}
                      className="assetPreviewFaceBox"
                      style={{ left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%` }}
                      title={face.person_name || "Detected face"}
                    >
                      <span className="assetPreviewFaceLabel">{face.person_name || "Unknown"}</span>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {isAudioAsset(previewAsset) && previewAsset.playback_url && (
            <audio
              controls
              preload="metadata"
              src={resolveApiUrl(previewAsset.playback_url)}
              style={{ width: "100%", marginTop: "0.6rem" }}
            />
          )}

          {isPdfAsset(previewAsset) && (
            <iframe
              title={previewAsset.title || previewAsset.original_filename || `Asset ${previewAsset.id}`}
              src={resolveApiUrl(`${previewAsset.download_url}?download=false`)}
              className="assetPreviewFrame"
            />
          )}

          {!isImageAsset(previewAsset) && !isAudioAsset(previewAsset) && !isPdfAsset(previewAsset) && (
            <div className="assetPreviewFallback">
              <p className="meta">Preview not available for this file type. Use View or Download for full details.</p>
            </div>
          )}

          <div className="assetPreviewMeta">
            <p className="meta"><strong>Filename:</strong> {previewAsset.original_filename || "none"}</p>
            {previewAsset.gemini_suggested_title && (
              <p className="meta"><strong>Gemini Suggested Title:</strong> {previewAsset.gemini_suggested_title}</p>
            )}
            {formatAssetCaptureDate(previewAsset) && <p className="meta"><strong>Captured:</strong> {formatAssetCaptureDate(previewAsset)}</p>}
            {previewAsset.exif_place_name && <p className="meta"><strong>EXIF Place:</strong> {previewAsset.exif_place_name}</p>}
            {previewAsset.reverse_geocode_location_name && (
              <p className="meta"><strong>Reverse Geocode:</strong> {previewAsset.reverse_geocode_location_name}</p>
            )}
            {previewAsset.analyzed_place_name && <p className="meta"><strong>Gemini Assessed Place:</strong> {previewAsset.analyzed_place_name}</p>}
            {!previewAsset.reverse_geocode_location_name && previewAsset.location_name && (
              <p className="meta"><strong>Place:</strong> {previewAsset.location_name}</p>
            )}
            <p className="meta">
              <strong>Position:</strong> {previewPositionText}
              {previewMapUrl && (
                <>
                  {" "}
                  <a href={previewMapUrl} target="_blank" rel="noreferrer">Map</a>
                </>
              )}
            </p>
            {!previewAsset.reverse_geocode_location_name && formatAssetGps(previewAsset) && (
              <p className="meta"><strong>Location:</strong> {formatAssetGps(previewAsset)}</p>
            )}
            {renderImageMetadataBadges(previewAsset)}
            {(previewAsset.image_width !== null || previewAsset.image_height !== null) && (
              <p className="meta"><strong>Dimensions:</strong> {previewAsset.image_width || "?"} x {previewAsset.image_height || "?"}</p>
            )}
            {(previewAsset.camera_make || previewAsset.camera_model) && (
              <p className="meta"><strong>Camera:</strong> {[previewAsset.camera_make, previewAsset.camera_model].filter(Boolean).join(" ")}</p>
            )}
            {modalEditingNotesId === previewAsset.id ? (
              <div className="controls" style={{ marginTop: "0.35rem" }}>
                <label style={{ display: "block", marginBottom: "0.25rem" }}><strong>Notes</strong></label>
                <input
                  className="directoryInput"
                  type="text"
                  value={modalEditingNotesValue}
                  autoFocus
                  onChange={(e) => setModalEditingNotesValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      void saveAssetNotes(previewAsset.id, eventId);
                      setModalEditingNotesId(null);
                    }
                    if (e.key === "Escape") {
                      setModalEditingNotesId(null);
                      setModalEditingNotesValue("");
                    }
                  }}
                  style={{ flex: 1, width: "100%" }}
                />
                <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.35rem" }}>
                  <button className="primary" type="button" onClick={() => { void saveAssetNotes(previewAsset.id, eventId); setModalEditingNotesId(null); }} disabled={assetNotesSavingId === previewAsset.id}>Save</button>
                  <button className="secondary" type="button" onClick={() => { setModalEditingNotesId(null); setModalEditingNotesValue(""); }}>Cancel</button>
                </div>
              </div>
            ) : (
              <div style={{ marginTop: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong>Notes</strong>
                  <button className="secondary" type="button" style={{ padding: "0.1rem 0.55rem", fontSize: "0.8rem" }} onClick={() => { setModalEditingNotesId(previewAsset.id); setModalEditingNotesValue(previewAsset.notes || ""); }}>Edit</button>
                </div>
                <p className="meta">{previewAsset.notes || "none"}</p>
              </div>
            )}
            {previewAsset.text_excerpt && <p className="meta assetTranscript"><strong>Transcript:</strong> {previewAsset.text_excerpt}</p>}
          </div>

          <div className="assetPreviewActions">
            <a className="secondary linkButton" href={resolveApiUrl(`${previewAsset.download_url}?download=false`)} target="_blank" rel="noreferrer">
              View
            </a>
            <a className="secondary linkButton" href={resolveApiUrl(`${previewAsset.download_url}?download=true`)}>
              Download
            </a>
            <button className="ghost" type="button" onClick={() => { void deleteAsset(previewAsset.id, eventId); handleCloseModal(); }}>
              Delete
            </button>
          </div>

          {showLinkControls && setAssetLinkTargets && linkUnlinkedAssetToEvent && (
            <div className="lifeAssetLinkControls" style={{ marginTop: "1rem", borderTop: "1px solid var(--border)", paddingTop: "0.75rem" }}>
              <select
                className="directoryInput"
                value={assetLinkTargets[previewAsset.id] || ""}
                onChange={(e) => setAssetLinkTargets((current) => ({ ...current, [previewAsset.id]: e.target.value }))}
                disabled={isSavingLifeStructure || lifeEvents.length === 0}
              >
                <option value="">Select event to link to</option>
                {lifeEvents.map((event) => (
                  <option key={event.id} value={event.id}>{event.title}</option>
                ))}
              </select>
              <button
                className="secondary"
                type="button"
                onClick={() => { void linkUnlinkedAssetToEvent(previewAsset.id); handleCloseModal(); }}
                disabled={!assetLinkTargets[previewAsset.id] || isSavingLifeStructure}
                style={{ marginTop: "0.5rem" }}
              >
                Link
              </button>
            </div>
          )}
        </div>
      </div>
    )}
    </>
  );
}
