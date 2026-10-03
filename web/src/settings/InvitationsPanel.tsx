import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, unwrap } from "../api/client";
import type { CreatedInvitation, Role } from "../api/types";
import { ErrorText, Field } from "../components/Form";

const KEY = ["invitations"];

function InviteForm({ onMade }: { onMade: (made: CreatedInvitation) => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("contributor");
  const [executor, setExecutor] = useState(false);
  const queryClient = useQueryClient();
  const invite = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/invitations", {
          body: { email, role, is_executor: executor },
        }),
      ),
    onSuccess: (made) => {
      queryClient.invalidateQueries({ queryKey: KEY });
      setEmail("");
      onMade(made);
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    invite.mutate();
  }
  return (
    <form onSubmit={submit}>
      <Field
        label="Email"
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <label>
        Role{" "}
        <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
          <option value="contributor">
            Contributor: records and organises
          </option>
          <option value="viewer">Viewer: browses and listens</option>
          <option value="owner">Owner: also manages people</option>
        </select>
      </label>
      <label>
        <input
          type="checkbox"
          checked={executor}
          onChange={(e) => setExecutor(e.target.checked)}
        />{" "}
        Executor (carries out the storytellers&apos; wishes later)
      </label>
      <ErrorText error={invite.error} />
      <button type="submit" className="primary" disabled={invite.isPending}>
        Make an invitation link
      </button>
    </form>
  );
}

/** Make, show once, list and revoke invitations. */
export function InvitationsPanel() {
  const [made, setMade] = useState<CreatedInvitation | null>(null);
  const queryClient = useQueryClient();
  const pending = useQuery({
    queryKey: KEY,
    queryFn: async () => unwrap(await api.GET("/api/invitations")),
  });
  const revoke = useMutation({
    mutationFn: async (id: number) => {
      await api.DELETE("/api/invitations/{invitation_id}", {
        params: { path: { invitation_id: id } },
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
  return (
    <section aria-labelledby="invite-title">
      <h2 id="invite-title">Invite someone</h2>
      <InviteForm onMade={setMade} />
      {made ? (
        <p role="status">
          Send {made.email} this link. It works once, for 7 days, and is shown
          only now: <code>{made.link}</code>
        </p>
      ) : null}
      <h3>Waiting to be accepted</h3>
      <ul>
        {pending.data?.map((inv) => (
          <li key={inv.id}>
            {inv.email}, {inv.role}, until{" "}
            {new Date(inv.expires_at).toLocaleDateString()}{" "}
            <button type="button" onClick={() => revoke.mutate(inv.id)}>
              Revoke
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
