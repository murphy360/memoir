"use client";

import { useEffect, useState } from "react";
import { DirectoryEntry, MemoryEntry } from "../types";

type MemoryCardProps = {
  memory: MemoryEntry;
  peopleOptions: DirectoryEntry[];
  formatBytes: (bytes: number) => string;
  resolveApiUrl: (path: string) => string;
  onReanalyze: (memoryId: number) => Promise<void>;
  onDelete: (memoryId: number) => Promise<void>;
  onAssignRecorder: (memoryId: number, personId: number) => Promise<void>;
  isBusy: boolean;
};

function asLabelList(items: string[]): string {
  if (items.length === 0) {
    return "Unknown";
  }
  return items.join(", ");
}

export function MemoryCard({
  memory,
  peopleOptions,
  formatBytes,
  resolveApiUrl,
  onReanalyze,
  onDelete,
  onAssignRecorder,
  isBusy,
}: MemoryCardProps) {
  const [selectedRecorder, setSelectedRecorder] = useState("");

  useEffect(() => {
    setSelectedRecorder(memory.recorder_person_id ? `${memory.recorder_person_id}` : "");
  }, [memory.id, memory.recorder_person_id]);

  const canAssignRecorder = !memory.recorder_name && selectedRecorder;

  return (
    <article className="memory">
      <h3>{memory.event_description}</h3>
      {memory.response_to_question_text && (
        <p className="memoryResponseLink">
          <strong>In response to:</strong> {memory.response_to_question_text}
        </p>
      )}
      <div className="metaList">
        <p className="meta">
          Date: <span className="badge">{memory.estimated_date_text || "Unknown"}</span>
        </p>
        <p className="meta">
          Date precision: <span className="badge">{memory.date_precision || "unknown"}</span>
        </p>
        <p className="meta">
          Recorded by: <span className="badge">{memory.recorder_name || "Unknown"}</span>
        </p>
        <p className="meta">
          Locations: <span className="badge">{asLabelList(memory.referenced_locations || [])}</span>
        </p>
        <p className="meta">
          People: <span className="badge">{asLabelList(memory.referenced_people || [])}</span>
        </p>
        <p className="meta">
          Tone: <span className="badge">{memory.emotional_tone}</span>
        </p>
        <p className="meta">
          Date recorded: <span className="badge">{memory.date_recorded || "Unknown"}</span>
        </p>
      </div>

      {!memory.recorder_name && (
        <div className="recorderAssign">
          <label className="meta" htmlFor={`recorder-${memory.id}`}>
            Assign recorder
          </label>
          <div className="recorderAssignControls">
            <select
              id={`recorder-${memory.id}`}
              className="micSelect"
              value={selectedRecorder}
              onChange={(event) => setSelectedRecorder(event.target.value)}
              disabled={isBusy || peopleOptions.length === 0}
            >
              <option value="">Select a person</option>
              {peopleOptions.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
            <button
              className="secondary"
              type="button"
              onClick={() => onAssignRecorder(memory.id, Number(selectedRecorder))}
              disabled={!canAssignRecorder || isBusy}
            >
              Save Recorder
            </button>
          </div>
          {peopleOptions.length === 0 && (
            <p className="meta">No known people are available yet to assign as the recorder.</p>
          )}
        </div>
      )}

      {memory.audio_size_bytes !== null && (
        <p className="meta">Stored audio size: {formatBytes(memory.audio_size_bytes)}</p>
      )}
      {memory.audio_url && (
        <audio controls preload="metadata" src={resolveApiUrl(memory.audio_url)} style={{ width: "100%" }} />
      )}
      <p>{memory.transcript}</p>
      <div className="memoryActions">
        <button className="secondary" type="button" onClick={() => onReanalyze(memory.id)} disabled={isBusy}>
          Reanalyze
        </button>
        <button className="ghost" type="button" onClick={() => onDelete(memory.id)} disabled={isBusy}>
          Delete
        </button>
      </div>
    </article>
  );
}
