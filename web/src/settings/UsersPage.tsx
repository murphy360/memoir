import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, unwrap } from "../api/client";
import type { Role, UserOut } from "../api/types";
import { ErrorText } from "../components/Form";
import { useMe } from "../auth/useMe";
import { InvitationsPanel } from "./InvitationsPanel";

const KEY = ["users"];

function UserRow({ user, isMe }: { user: UserOut; isMe: boolean }) {
  const queryClient = useQueryClient();
  const [temporary, setTemporary] = useState("");
  const done = () => queryClient.invalidateQueries({ queryKey: KEY });
  const update = useMutation({
    mutationFn: async (body: { role?: Role; is_executor?: boolean }) =>
      unwrap(
        await api.PATCH("/api/users/{user_id}", {
          params: { path: { user_id: user.id } },
          body,
        }),
      ),
    onSuccess: done,
  });
  const reset = useMutation({
    mutationFn: async () => {
      const result = await api.POST("/api/users/{user_id}/temporary-password", {
        params: { path: { user_id: user.id } },
        body: { password: temporary },
      });
      if (result.error !== undefined) unwrap(result);
    },
    onSuccess: () => setTemporary(""),
  });
  const remove = useMutation({
    mutationFn: async () => {
      const result = await api.DELETE("/api/users/{user_id}", {
        params: { path: { user_id: user.id } },
      });
      if (result.error !== undefined) unwrap(result);
    },
    onSuccess: done,
  });
  const error = update.error ?? reset.error ?? remove.error;
  return (
    <li>
      <strong>{user.display_name}</strong> ({user.email}){isMe ? ", you" : ""}{" "}
      <select
        aria-label={`Role for ${user.display_name}`}
        value={user.role}
        onChange={(e) => update.mutate({ role: e.target.value as Role })}
      >
        <option value="owner">Owner</option>
        <option value="contributor">Contributor</option>
        <option value="viewer">Viewer</option>
      </select>{" "}
      <label>
        <input
          type="checkbox"
          checked={user.is_executor}
          onChange={(e) => update.mutate({ is_executor: e.target.checked })}
        />{" "}
        Executor
      </label>
      {!isMe ? (
        <span>
          {" "}
          <input
            aria-label={`Temporary password for ${user.display_name}`}
            type="text"
            value={temporary}
            onChange={(e) => setTemporary(e.target.value)}
          />{" "}
          <button
            type="button"
            onClick={() => reset.mutate()}
            disabled={!temporary}
          >
            Set temporary password
          </button>{" "}
          <button
            type="button"
            onClick={() => {
              if (
                window.confirm(
                  `Remove ${user.display_name}? They are signed out at once.`,
                )
              )
                remove.mutate();
            }}
          >
            Remove
          </button>
        </span>
      ) : null}
      {reset.isSuccess ? (
        <span role="status">
          {" "}
          They must choose a new one when they sign in.
        </span>
      ) : null}
      <ErrorText error={error} />
    </li>
  );
}

/** The owner's page: who is in the archive, and who is invited. */
export function UsersPage() {
  const me = useMe();
  const users = useQuery({
    queryKey: KEY,
    queryFn: async () => unwrap(await api.GET("/api/users")),
  });
  return (
    <section>
      <h1>People with access</h1>
      <ul className="users">
        {users.data?.map((u) => (
          <UserRow key={u.id} user={u} isMe={u.id === me.data?.id} />
        ))}
      </ul>
      <InvitationsPanel />
    </section>
  );
}
