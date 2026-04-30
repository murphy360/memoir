import { MemoryEntry } from "../types";

type MemoryCardProps = {
  memory: MemoryEntry;
  formatBytes: (bytes: number) => string;
  resolveApiUrl: (path: string) => string;
};

function asLabelList(items: string[]): string {
  if (items.length === 0) {
    return "Unknown";
  }
  return items.join(", ");
}

export function MemoryCard({ memory, formatBytes, resolveApiUrl }: MemoryCardProps) {
  return (
    <article className="memory">
      <h3>{memory.event_description}</h3>
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
      </div>

      {memory.audio_size_bytes !== null && (
        <p className="meta">Stored audio size: {formatBytes(memory.audio_size_bytes)}</p>
      )}
      {memory.audio_url && (
        <audio controls preload="metadata" src={resolveApiUrl(memory.audio_url)} style={{ width: "100%" }} />
      )}
      <p>{memory.transcript}</p>
    </article>
  );
}
