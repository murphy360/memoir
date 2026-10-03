import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";

import { api, unwrap } from "../../api/client";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorText } from "../../components/Form";
import { useToast } from "../../components/Toast";
import { messageOf } from "../../lib/errors";
import { SavedToLine } from "../place/SavedToLine";
import { describe } from "../place/api";

/** Waiting to be placed: each memory with Memoir's suggestion and a one-tap Place. */
export function InboxPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const inbox = useQuery({
    queryKey: ["inbox"],
    queryFn: async () => unwrap(await api.GET("/api/inbox")),
  });
  const accept = useMutation({
    mutationFn: async (memoryId: number) =>
      unwrap(
        await api.POST("/api/inbox/{memory_id}/accept", {
          params: { path: { memory_id: memoryId } },
        }),
      ),
    onSuccess: (placed) => {
      queryClient.invalidateQueries({ queryKey: ["inbox"] });
      if (placed.saved_to)
        toast(`Saved to ${describe(placed.saved_to)}`, "success");
    },
    onError: (error) => toast(messageOf(error), "error"),
  });
  const items = inbox.data?.items ?? [];
  return (
    <section aria-labelledby="inbox-title">
      <h1 id="inbox-title">Waiting to be placed</h1>
      <p className="hint">
        Memories that are not on the timeline yet. Place each one where it
        happened.
      </p>
      <ErrorText error={inbox.error} />
      {inbox.data && !items.length ? (
        <EmptyState title="Nothing is waiting">
          Every memory is on the timeline.
        </EmptyState>
      ) : null}
      <ul className="inbox">
        {items.map(({ memory, suggestion }) => (
          <li key={memory.id}>
            <Link to={`/memories/${memory.id}`}>
              <strong>{memory.title ?? "A memory"}</strong>
            </Link>
            {memory.date_text ? (
              <span className="hint"> {memory.date_text}</span>
            ) : null}
            {suggestion ? (
              <div className="row">
                <Button
                  variant="primary"
                  busy={accept.isPending && accept.variables === memory.id}
                  onClick={() => accept.mutate(memory.id)}
                >
                  Place in {suggestion.label}
                </Button>
              </div>
            ) : (
              <SavedToLine memoryId={memory.id} />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
