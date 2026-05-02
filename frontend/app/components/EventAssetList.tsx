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
  return (
    <div className="lifeAssetList">
      {assets.map((asset) => (
        <div
          key={asset.id}
          id={`asset-row-${asset.id}`}
          className={`lifeAssetRow${highlightedElementId === `asset-row-${asset.id}` ? " focusPulse" : ""}`}
        >
          <div className="assetRowHeader">
            <span style={{ flex: 1, minWidth: 0 }}>
              <strong>{asset.title || asset.original_filename || `Asset ${asset.id}`}</strong>
              <span className="meta"> · {asset.kind}{asset.size_bytes ? ` · ${formatBytes(asset.size_bytes)}` : ""}</span>
            </span>
            <button
              className="secondary"
              type="button"
              style={{ padding: "0.1rem 0.55rem", fontSize: "0.8rem", flexShrink: 0 }}
              onClick={() => setExpandedAssetRowIds((prev) => {
                const next = new Set(prev);
                if (next.has(asset.id)) next.delete(asset.id); else next.add(asset.id);
                return next;
              })}
            >
              {expandedAssetRowIds.has(asset.id) ? "Collapse" : "Expand"}
            </button>
          </div>
          {expandedAssetRowIds.has(asset.id) && <div>
            {editingAssetTitleId === asset.id ? (
              <div className="controls" style={{ marginBottom: "0.35rem" }}>
                <input
                  className="directoryInput"
                  type="text"
                  value={editingAssetTitleValue}
                  autoFocus
                  onChange={(e) => setEditingAssetTitleValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      void saveAssetTitle(asset.id, eventId);
                    }
                    if (e.key === "Escape") {
                      setEditingAssetTitleId(null);
                      setEditingAssetTitleValue("");
                    }
                  }}
                  style={{ flex: 1 }}
                />
                <button className="primary" type="button" onClick={() => void saveAssetTitle(asset.id, eventId)} disabled={assetTitleSavingId === asset.id}>Save</button>
                <button className="secondary" type="button" onClick={() => { setEditingAssetTitleId(null); setEditingAssetTitleValue(""); }}>Cancel</button>
              </div>
            ) : (
              <div className="assetNotesRow" style={{ marginTop: 0 }}>
                <span className="meta">Title</span>
                <button
                  className="secondary"
                  type="button"
                  style={{ padding: "0.1rem 0.55rem", fontSize: "0.8rem" }}
                  onClick={() => {
                    setEditingAssetTitleId(asset.id);
                    setEditingAssetTitleValue(asset.title || "");
                  }}
                >
                  Edit Title
                </button>
              </div>
            )}
            <p className="meta">Filename: {asset.original_filename || "none"}</p>
            {asset.kind === "photo" && (
              <img
                src={resolveApiUrl(`${asset.download_url}?download=false`)}
                alt={asset.title || asset.original_filename || `Asset ${asset.id}`}
                className="assetThumbnail"
              />
            )}
            <p className="meta">Kind: {asset.kind} {asset.size_bytes ? `| ${formatBytes(asset.size_bytes)}` : ""}</p>
            {renderImageMetadataBadges(asset)}
            {(asset.image_width !== null || asset.image_height !== null) && (
              <p className="meta">Dimensions: {asset.image_width || "?"} x {asset.image_height || "?"}</p>
            )}
            {formatAssetCaptureDate(asset) && (
              <p className="meta">Captured: {formatAssetCaptureDate(asset)}</p>
            )}
            {formatAssetGps(asset) && (
              <p className="meta">Location: {formatAssetGps(asset)}</p>
            )}
            {(asset.camera_make || asset.camera_model) && (
              <p className="meta">Camera: {[asset.camera_make, asset.camera_model].filter(Boolean).join(" ")}</p>
            )}
            {editingAssetNotesId === asset.id ? (
              <div className="controls" style={{ marginTop: "0.35rem" }}>
                <input
                  className="directoryInput"
                  type="text"
                  value={editingAssetNotesValue}
                  autoFocus
                  onChange={(e) => setEditingAssetNotesValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      void saveAssetNotes(asset.id, eventId);
                    }
                    if (e.key === "Escape") {
                      setEditingAssetNotesId(null);
                      setEditingAssetNotesValue("");
                    }
                  }}
                  style={{ flex: 1 }}
                />
                <button className="primary" type="button" onClick={() => void saveAssetNotes(asset.id, eventId)} disabled={assetNotesSavingId === asset.id}>Save</button>
                <button className="secondary" type="button" onClick={() => { setEditingAssetNotesId(null); setEditingAssetNotesValue(""); }}>Cancel</button>
              </div>
            ) : (
              <div className="assetNotesRow">
                <p className="meta">Notes: {asset.notes || "none"}</p>
                <button
                  className="secondary"
                  type="button"
                  style={{ padding: "0.1rem 0.55rem", fontSize: "0.8rem" }}
                  onClick={() => {
                    setEditingAssetNotesId(asset.id);
                    setEditingAssetNotesValue(asset.notes || "");
                  }}
                >
                  Edit Notes
                </button>
              </div>
            )}
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
          </div>}
          {expandedAssetRowIds.has(asset.id) && !showLinkControls && <div className="assetActions">
            <a className="secondary linkButton" href={resolveApiUrl(`${asset.download_url}?download=false`)} target="_blank" rel="noreferrer">
              View
            </a>
            <a className="secondary linkButton" href={resolveApiUrl(`${asset.download_url}?download=true`)}>
              Download
            </a>
            <button
              className="ghost"
              type="button"
              onClick={() => void deleteAsset(asset.id, eventId)}
            >
              Delete
            </button>
          </div>}
          {expandedAssetRowIds.has(asset.id) && showLinkControls && setAssetLinkTargets && linkUnlinkedAssetToEvent && <div className="lifeAssetLinkControls">
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
              onClick={() => void linkUnlinkedAssetToEvent(asset.id)}
              disabled={!assetLinkTargets[asset.id] || isSavingLifeStructure}
            >
              Link
            </button>
            <a className="ghost linkButton" href={resolveApiUrl(`${asset.download_url}?download=false`)} target="_blank" rel="noreferrer">
              View
            </a>
            <a className="ghost linkButton" href={resolveApiUrl(`${asset.download_url}?download=true`)}>
              Download
            </a>
            <button
              className="ghost"
              type="button"
              onClick={() => void deleteAsset(asset.id)}
            >
              Delete
            </button>
          </div>}
        </div>
      ))}
    </div>
  );
}
