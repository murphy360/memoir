import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { api, unwrap } from "../../api/client";
import { DeleteMemory } from "../memories/DeleteMemory";
import { SavedToLine } from "../place/SavedToLine";

/** Transcription states after which the words will not change on their own. */
const SETTLED = new Set(["done", "empty", "failed", "ai_off", "manual"]);

/**
 * What became of a recording once it is a memory: where it was saved, or, when nothing
 * was said (Record tapped and stopped), an offer to delete it.
 */
export function AfterUpload({ memoryId }: { memoryId: number }) {
  const [deleted, setDeleted] = useState(false);
  const memory = useQuery({
    queryKey: ["memory", memoryId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/memories/{memory_id}", {
          params: { path: { memory_id: memoryId } },
        }),
      ),
    refetchInterval: (q) =>
      !SETTLED.has(q.state.data?.transcript_state ?? "") &&
      q.state.dataUpdateCount < 60
        ? 3000
        : false,
  });
  if (deleted) return <p role="status">Deleted. Nothing was kept.</p>;
  if (memory.data?.transcript_state === "empty") {
    return (
      <div className="warning" role="status">
        <p>Nothing was heard in that recording.</p>
        <DeleteMemory
          memoryId={memoryId}
          label="Delete it"
          onDeleted={() => setDeleted(true)}
        />
      </div>
    );
  }
  return (
    <>
      <SavedToLine memoryId={memoryId} waiting />
      <Link to={`/memories/${memoryId}`}>Open the memory</Link>
    </>
  );
}
