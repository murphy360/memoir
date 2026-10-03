import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router";

import { api, unwrap } from "../api/client";
import { ErrorText, Field } from "../components/Form";
import { ME } from "./useMe";

/** The page an invitation link opens: see who invited you, pick a name and a password. */
export function InvitePage() {
  const { token = "" } = useParams();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const preview = useQuery({
    queryKey: ["invitation", token],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/invitations/accept/{token}", {
          params: { path: { token } },
        }),
      ),
    retry: false,
  });
  const accept = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/invitations/accept/{token}", {
          params: { path: { token } },
          body: { display_name: name, password },
        }),
      ),
    onSuccess: (user) => {
      queryClient.setQueryData(ME, user);
      navigate("/", { replace: true });
    },
  });

  if (preview.isPending) return <p role="status">Opening your invitation…</p>;
  if (preview.isError) {
    return (
      <main className="narrow">
        <h1>Invitation</h1>
        <ErrorText error={preview.error} />
      </main>
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    accept.mutate();
  }

  const invite = preview.data;
  return (
    <main className="narrow">
      <h1>Join {invite.archive_name}</h1>
      <p>
        {invite.invited_by ?? "The family"} invited {invite.email} as a{" "}
        {invite.role}.
      </p>
      <form onSubmit={submit}>
        <Field
          label="Your name, as the family knows it"
          autoComplete="name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Field
          label="Choose a password"
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          hint="At least 12 characters. A few words you will remember work well."
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <ErrorText error={accept.error} />
        <button type="submit" className="primary" disabled={accept.isPending}>
          Join
        </button>
      </form>
    </main>
  );
}
