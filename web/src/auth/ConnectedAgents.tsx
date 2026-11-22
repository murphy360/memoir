import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";
import { Button } from "../components/Button";
import { useConfirm } from "../components/Confirm";
import { useToast } from "../components/Toast";
import { messageOf } from "../lib/errors";

const AGENTS = ["me", "agents"];

type Agent = { id: number; name: string };

function when(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString() : "not yet";
}

/**
 * The assistants that may act as you (docs/AGENTS_MCP.md), each with Disconnect. A
 * disconnected agent's next call is refused.
 */
export function ConnectedAgents() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { confirm, element } = useConfirm();
  const agents = useQuery({
    queryKey: AGENTS,
    queryFn: async () => unwrap(await api.GET("/api/me/agents")),
  });
  const disconnect = useMutation({
    mutationFn: async (agent: Agent) => {
      // 204 has no body: only an error answer is unwrapped (to throw it).
      const result = await api.DELETE("/api/me/agents/{agent_id}", {
        params: { path: { agent_id: agent.id } },
      });
      if (result.error !== undefined) unwrap(result);
      return agent;
    },
    onSuccess: (agent) => {
      void queryClient.invalidateQueries({ queryKey: AGENTS });
      toast(`${agent.name} is disconnected.`, "success");
    },
    onError: (error) => toast(messageOf(error), "error"),
  });
  async function ask(agent: Agent) {
    const ok = await confirm({
      title: `Disconnect ${agent.name}?`,
      body: `${agent.name} can no longer read or tell stories as you. The stories it told stay in Memoir.`,
      confirm: "Disconnect",
      danger: true,
    });
    if (ok) disconnect.mutate(agent);
  }
  const list = agents.data ?? [];
  return (
    <section aria-labelledby="agents-title">
      <h2 id="agents-title">Connected agents</h2>
      {list.length === 0 ? (
        <p className="hint">
          No assistant is connected. To tell stories through Claude or another
          assistant, add Memoir to it as a connector.
        </p>
      ) : (
        <ul>
          {list.map((a) => (
            <li key={a.id}>
              <strong>{a.name}</strong>, connected {when(a.connected_at)}, last
              used {when(a.last_used_at)}{" "}
              <Button
                variant="danger"
                busy={disconnect.isPending && disconnect.variables?.id === a.id}
                onClick={() => void ask(a)}
                aria-label={`Disconnect ${a.name}`}
              >
                Disconnect
              </Button>
            </li>
          ))}
        </ul>
      )}
      {element}
    </section>
  );
}
