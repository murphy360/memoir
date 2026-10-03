import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "../../components/Button";
import { describe, loadPlacement, placementKey } from "./api";
import { PlacementSheet } from "./PlacementSheet";

/**
 * Where a memory went, in plain words, with one tap to change it (requirements 5.3).
 * Shown after recording and on the memory itself.
 */
export function SavedToLine({
  memoryId,
  waiting = false,
}: {
  memoryId: number;
  /** Just recorded: keep looking while Memoir works out where it goes. */
  waiting?: boolean;
}) {
  const [choosing, setChoosing] = useState(false);
  const placement = useQuery({
    queryKey: placementKey(memoryId),
    queryFn: () => loadPlacement(memoryId),
    refetchInterval: (q) =>
      waiting && !q.state.data?.saved_to && q.state.dataUpdateCount < 60
        ? 3000
        : false,
  });
  const saved = placement.data?.saved_to;
  return (
    <div className="saved-to">
      {saved ? (
        <p role="status">
          Saved to <strong>{describe(saved)}</strong>
          {saved.created_for_this_memory ? (
            <span className="hint"> (created for this memory)</span>
          ) : null}
        </p>
      ) : placement.data ? (
        <p role="status">Waiting to be placed.</p>
      ) : null}
      {placement.data ? (
        <Button onClick={() => setChoosing(true)}>
          {saved ? "Change" : "Place it"}
        </Button>
      ) : null}
      {choosing && placement.data ? (
        <PlacementSheet
          memoryId={memoryId}
          placement={placement.data}
          onClose={() => setChoosing(false)}
        />
      ) : null}
    </div>
  );
}
