"use client";

import { useEffect, useState } from "react";
import { DirectoryEntry } from "../types";

type DirectoryManagerProps = {
  title: string;
  addLabel: string;
  emptyLabel: string;
  items: DirectoryEntry[];
  isBusy: boolean;
  onCreate: (name: string) => Promise<void>;
  onRename: (itemId: number, name: string) => Promise<void>;
  onDelete: (itemId: number) => Promise<void>;
  onMerge?: (sourceId: number, intoId: number) => Promise<void>;
  onSplit?: (sourceId: number, newNames: string[], keepAlias: boolean) => Promise<void>;
  onAddAlias?: (itemId: number, alias: string) => Promise<void>;
  onRemoveAlias?: (itemId: number, alias: string) => Promise<void>;
};

export function DirectoryManager({
  title,
  addLabel,
  emptyLabel,
  items,
  isBusy,
  onCreate,
  onRename,
  onDelete,
  onMerge,
  onSplit,
  onAddAlias,
  onRemoveAlias,
}: DirectoryManagerProps) {
  const [newName, setNewName] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");
  const [mergingId, setMergingId] = useState<number | null>(null);
  const [mergeTargetId, setMergeTargetId] = useState("");
  const [splittingId, setSplittingId] = useState<number | null>(null);
  const [splitNames, setSplitNames] = useState("");
  const [splitKeepAlias, setSplitKeepAlias] = useState(true);
  const [addingAliasId, setAddingAliasId] = useState<number | null>(null);
  const [newAlias, setNewAlias] = useState("");

  useEffect(() => {
    const editingStillExists = editingId === null || items.some((item) => item.id === editingId);
    if (!editingStillExists) {
      setEditingId(null);
      setEditingName("");
    }

    const mergingStillExists = mergingId === null || items.some((item) => item.id === mergingId);
    if (!mergingStillExists) {
      setMergingId(null);
      setMergeTargetId("");
    }

    const splittingStillExists = splittingId === null || items.some((item) => item.id === splittingId);
    if (!splittingStillExists) {
      setSplittingId(null);
      setSplitNames("");
    }
  }, [editingId, mergingId, splittingId, items]);

  return (
    <section className="directoryCard">
      <div className="directoryHeader">
        <h2>{title}</h2>
        <span className="meta">{items.length} total</span>
      </div>

      <div className="directoryCreateRow">
        <input
          className="directoryInput"
          type="text"
          value={newName}
          onChange={(event) => setNewName(event.target.value)}
          placeholder={addLabel}
          disabled={isBusy}
        />
        <button
          className="secondary"
          type="button"
          disabled={isBusy || !newName.trim()}
          onClick={async () => {
            await onCreate(newName);
            setNewName("");
          }}
        >
          Add
        </button>
      </div>

      <div className="directoryList">
        {items.length === 0 && <p className="meta">{emptyLabel}</p>}
        {items.map((item) => {
          const isEditing = editingId === item.id;
          const isMerging = mergingId === item.id;
          const isSplitting = splittingId === item.id;
          const isAddingAlias = addingAliasId === item.id;
          const mergeTargets = items.filter((other) => other.id !== item.id);

          return (
            <div key={item.id} className="directoryRow">
              <div className="directoryRowMain">
                {isEditing ? (
                  <input
                    className="directoryInput"
                    type="text"
                    value={editingName}
                    onChange={(event) => setEditingName(event.target.value)}
                    disabled={isBusy}
                  />
                ) : (
                  <div className="directoryNameBlock">
                    <span className="directoryName">{item.name}</span>
                    {item.aliases && item.aliases.length > 0 && (
                      <div className="aliasList">
                        {item.aliases.map((alias) => (
                          <span key={alias} className="aliasChip">
                            {alias}
                            {onRemoveAlias && (
                              <button
                                className="aliasRemove"
                                type="button"
                                aria-label={`Remove alias ${alias}`}
                                disabled={isBusy}
                                onClick={() => onRemoveAlias(item.id, alias)}
                              >
                                ×
                              </button>
                            )}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                <span className="badge">{item.memory_count} memories</span>
              </div>

              {isMerging && (
                <div className="directoryMergeRow">
                  <span className="meta">Merge <strong>{item.name}</strong> into:</span>
                  <select
                    className="directoryInput"
                    value={mergeTargetId}
                    onChange={(event) => setMergeTargetId(event.target.value)}
                    disabled={isBusy}
                  >
                    <option value="">Select target person</option>
                    {mergeTargets.map((target) => (
                      <option key={target.id} value={target.id}>
                        {target.name} ({target.memory_count} memories)
                      </option>
                    ))}
                  </select>
                  <button
                    className="secondary"
                    type="button"
                    disabled={isBusy || !mergeTargetId}
                    onClick={async () => {
                      await onMerge!(item.id, Number(mergeTargetId));
                      setMergingId(null);
                      setMergeTargetId("");
                    }}
                  >
                    Confirm merge
                  </button>
                  <button
                    className="ghost"
                    type="button"
                    disabled={isBusy}
                    onClick={() => {
                      setMergingId(null);
                      setMergeTargetId("");
                    }}
                  >
                    Cancel
                  </button>
                </div>
              )}

              {isSplitting && (
                <div className="directoryMergeRow">
                  <span className="meta">Split <strong>{item.name}</strong> into (comma-separated names):</span>
                  <input
                    className="directoryInput"
                    type="text"
                    placeholder="e.g. Jack Murphy, Sue Murphy"
                    value={splitNames}
                    onChange={(event) => setSplitNames(event.target.value)}
                    disabled={isBusy}
                  />
                  <label className="aliasKeepLabel">
                    <input
                      type="checkbox"
                      checked={splitKeepAlias}
                      onChange={(e) => setSplitKeepAlias(e.target.checked)}
                      disabled={isBusy}
                    />
                    Keep &ldquo;{item.name}&rdquo; as alias on new people
                  </label>
                  <button
                    className="secondary"
                    type="button"
                    disabled={isBusy || !splitNames.trim()}
                    onClick={async () => {
                      const names = splitNames.split(",").map((n) => n.trim()).filter(Boolean);
                      await onSplit!(item.id, names, splitKeepAlias);
                      setSplittingId(null);
                      setSplitNames("");
                    }}
                  >
                    Confirm split
                  </button>
                  <button
                    className="ghost"
                    type="button"
                    disabled={isBusy}
                    onClick={() => {
                      setSplittingId(null);
                      setSplitNames("");
                    }}
                  >
                    Cancel
                  </button>
                </div>
              )}

              {isAddingAlias && onAddAlias && (
                <div className="directoryMergeRow">
                  <span className="meta">New alias for <strong>{item.name}</strong>:</span>
                  <input
                    className="directoryInput"
                    type="text"
                    placeholder="e.g. parents"
                    value={newAlias}
                    onChange={(event) => setNewAlias(event.target.value)}
                    disabled={isBusy}
                  />
                  <button
                    className="secondary"
                    type="button"
                    disabled={isBusy || !newAlias.trim()}
                    onClick={async () => {
                      await onAddAlias(item.id, newAlias.trim());
                      setAddingAliasId(null);
                      setNewAlias("");
                    }}
                  >
                    Save alias
                  </button>
                  <button
                    className="ghost"
                    type="button"
                    disabled={isBusy}
                    onClick={() => {
                      setAddingAliasId(null);
                      setNewAlias("");
                    }}
                  >
                    Cancel
                  </button>
                </div>
              )}

              <div className="directoryActions">
                {isEditing ? (
                  <>
                    <button
                      className="secondary"
                      type="button"
                      disabled={isBusy || !editingName.trim()}
                      onClick={async () => {
                        await onRename(item.id, editingName);
                        setEditingId(null);
                        setEditingName("");
                      }}
                    >
                      Save
                    </button>
                    <button
                      className="ghost"
                      type="button"
                      disabled={isBusy}
                      onClick={() => {
                        setEditingId(null);
                        setEditingName("");
                      }}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      className="ghost"
                      type="button"
                      disabled={isBusy}
                      onClick={() => {
                        setEditingId(item.id);
                        setEditingName(item.name);
                      }}
                    >
                      Rename
                    </button>
                    {onAddAlias && (
                      <button
                        className="ghost"
                        type="button"
                        disabled={isBusy}
                        onClick={() => {
                          setAddingAliasId(isAddingAlias ? null : item.id);
                          setNewAlias("");
                        }}
                      >
                        + Alias
                      </button>
                    )}
                    {onSplit && (
                      <button
                        className="ghost"
                        type="button"
                        disabled={isBusy}
                        onClick={() => {
                          setSplittingId(item.id);
                          setSplitNames("");
                        }}
                      >
                        Split
                      </button>
                    )}
                    {onMerge && items.length > 1 && (
                      <button
                        className="ghost"
                        type="button"
                        disabled={isBusy}
                        onClick={() => {
                          setMergingId(item.id);
                          setMergeTargetId("");
                        }}
                      >
                        Merge
                      </button>
                    )}
                    <button
                      className="ghost"
                      type="button"
                      disabled={isBusy}
                      onClick={() => onDelete(item.id)}
                    >
                      Delete
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}