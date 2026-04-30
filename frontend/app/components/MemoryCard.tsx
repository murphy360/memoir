"use client";

import { useEffect, useState } from "react";
import { DirectoryEntry, MemoryEntry } from "../types";

type MemoryCardProps = {
  memory: MemoryEntry;
  peopleOptions: DirectoryEntry[];
  formatBytes: (bytes: number) => string;
  resolveApiUrl: (path: string) => string;
  onResearch: (memoryId: number) => Promise<void>;
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
  onResearch,
  onReanalyze,
  onDelete,
  onAssignRecorder,
  isBusy,
}: MemoryCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedRecorder, setSelectedRecorder] = useState("");

  useEffect(() => {
    setSelectedRecorder(memory.recorder_person_id ? `${memory.recorder_person_id}` : "");
  }, [memory.id, memory.recorder_person_id]);

  const canAssignRecorder = !memory.recorder_name && selectedRecorder;

  return (
    <article className="memory">
      <div className="memoryHeader">
        <div className="memoryHeaderText">
          <h3>{memory.event_description}</h3>
          <div className="memoryDateSummary">
            <p className="meta">
              Date: <span className="badge">{memory.estimated_date_text || "Unknown"}</span>
            </p>
            <p className="meta">
              Recorded: <span className="badge">{memory.date_recorded || "Unknown"}</span>
            </p>
          </div>
        </div>
        <button
          className="secondary memoryToggle"
          type="button"
          onClick={() => setIsExpanded((current) => !current)}
          aria-expanded={isExpanded}
        >
          {isExpanded ? "Collapse" : "Expand"}
        </button>
      </div>

      {isExpanded && memory.response_to_question_text && (
        <p className="memoryResponseLink">
          <strong>In response to:</strong> {memory.response_to_question_text}
        </p>
      )}
      {isExpanded && <div className="metaList">
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
      </div>}

      {isExpanded && !memory.recorder_name && (
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

      {isExpanded && memory.audio_size_bytes !== null && (
        <p className="meta">Stored audio size: {formatBytes(memory.audio_size_bytes)}</p>
      )}
      {isExpanded && memory.audio_url && (
        <audio controls preload="metadata" src={resolveApiUrl(memory.audio_url)} style={{ width: "100%" }} />
      )}
      {isExpanded && <p>{memory.transcript}</p>}
      {isExpanded && memory.research_summary && (
        <section className="researchPanel">
          <p className="researchLabel">Research Notes</p>
          <pre className="researchSummary">{memory.research_summary}</pre>
          {memory.research_queries.length > 0 && (
            <div className="researchQueries">
              <p className="researchSubhead">Search queries used</p>
              <div className="researchQueryList">
                {memory.research_queries.map((query) => (
                  <span key={query} className="researchQueryChip">{query}</span>
                ))}
              </div>
            </div>
          )}
          {memory.research_sources.length > 0 && (
            <div className="researchSources">
              <p className="researchSubhead">Sources</p>
              <ul className="researchSourceList">
                {memory.research_sources.map((source) => (
                  <li key={source.url}>
                    <a href={source.url} target="_blank" rel="noreferrer">
                      {source.title}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
      {isExpanded && <div className="memoryActions">
        <button className="secondary" type="button" onClick={() => onResearch(memory.id)} disabled={isBusy}>
          {memory.research_summary ? "Refresh Research" : "Research"}
        </button>
        <button className="secondary" type="button" onClick={() => onReanalyze(memory.id)} disabled={isBusy}>
          Reanalyze
        </button>
        <button className="ghost" type="button" onClick={() => onDelete(memory.id)} disabled={isBusy}>
          Delete
        </button>
      </div>}
    </article>
  );
}
