import type { Dispatch, SetStateAction } from "react";
import { EventAssetList } from "./EventAssetList";
import type { AssetEntry, LifeEvent } from "../types";

type UnlinkedAssetsInboxProps = {
  unlinkedAssets: AssetEntry[];
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
  lifeEvents: LifeEvent[];
  assetLinkTargets: Record<number, string>;
  setAssetLinkTargets: Dispatch<SetStateAction<Record<number, string>>>;
  linkUnlinkedAssetToEvent: (assetId: number) => Promise<void>;
  isSavingLifeStructure: boolean;
};

export function UnlinkedAssetsInbox({
  unlinkedAssets,
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
  lifeEvents,
  assetLinkTargets,
  setAssetLinkTargets,
  linkUnlinkedAssetToEvent,
  isSavingLifeStructure,
}: UnlinkedAssetsInboxProps) {
  return (
    <article className="memory" style={{ marginTop: "0.75rem" }}>
      <h3>Unlinked Assets Inbox</h3>
      {unlinkedAssets.length === 0 ? (
        <p className="meta">No unlinked assets. Great job keeping context connected.</p>
      ) : (
        <EventAssetList
          assets={unlinkedAssets}
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
          showLinkControls
          lifeEvents={lifeEvents.map((event) => ({ id: event.id, title: event.title }))}
          assetLinkTargets={assetLinkTargets}
          setAssetLinkTargets={setAssetLinkTargets}
          linkUnlinkedAssetToEvent={linkUnlinkedAssetToEvent}
          isSavingLifeStructure={isSavingLifeStructure}
        />
      )}
    </article>
  );
}
