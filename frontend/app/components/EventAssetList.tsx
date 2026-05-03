import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import {
  formatAssetCaptureDate,
  formatAssetGps,
  renderImageMetadataBadges,
} from "../lib/homePageHelpers";
import type { AssetEntry } from "../types";

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

  const galleryAssets = useMemo(
    () => assets.filter((asset) => isImageAsset(asset) || isAudioAsset(asset) || isDocumentAsset(asset)),
    [assets],
  );

  const previewAsset = useMemo(
    () => assets.find((asset) => asset.id === previewAssetId) || null,
    [assets, previewAssetId],
  );

  const handleCloseModal = () => {
    setPreviewAssetId(null);
    setModalEditingTitleId(null);
    setModalEditingTitleValue("");
    setModalEditingNotesId(null);
    setModalEditingNotesValue("");
  };

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
            <img
              src={resolveApiUrl(`${previewAsset.download_url}?download=false`)}
              alt={previewAsset.title || previewAsset.original_filename || `Asset ${previewAsset.id}`}
              className="assetPreviewImage"
            />
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
            {formatAssetCaptureDate(previewAsset) && <p className="meta"><strong>Captured:</strong> {formatAssetCaptureDate(previewAsset)}</p>}
            {formatAssetGps(previewAsset) && <p className="meta"><strong>Location:</strong> {formatAssetGps(previewAsset)}</p>}
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
