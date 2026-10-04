import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { api, unwrap } from "../api/client";
import type { Me } from "../api/types";
import { ErrorText, Field } from "../components/Form";
import { ChangePasswordForm } from "./ChangePasswordPage";
import { ME, useMe } from "./useMe";

function NameForm({ me }: { me: Me }) {
  const [name, setName] = useState(me.display_name);
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: async () =>
      unwrap(await api.PATCH("/api/me", { body: { display_name: name } })),
    onSuccess: (user) => queryClient.setQueryData(ME, user),
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }
  return (
    <form onSubmit={submit}>
      <Field
        label="Your name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <ErrorText error={save.error} />
      <button type="submit" disabled={save.isPending}>
        {save.isSuccess ? "Saved" : "Save name"}
      </button>
    </form>
  );
}

function Sessions() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const sessions = useQuery({
    queryKey: ["me", "sessions"],
    queryFn: async () => unwrap(await api.GET("/api/me/sessions")),
  });
  const everywhere = useMutation({
    mutationFn: async () => {
      await api.POST("/api/auth/logout-all");
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["me", "sessions"] }),
  });
  const signOut = useMutation({
    mutationFn: async () => {
      await api.POST("/api/auth/logout");
    },
    onSuccess: () => {
      queryClient.setQueryData(ME, null);
      navigate("/login", { replace: true });
    },
  });
  return (
    <section aria-labelledby="sessions-title">
      <h2 id="sessions-title">Where you are signed in</h2>
      <ul>
        {sessions.data?.map((s) => (
          <li key={s.id}>
            {s.user_agent ?? "A browser"}, last used{" "}
            {new Date(s.last_seen_at).toLocaleString()}
            {s.current ? " (this one)" : ""}
          </li>
        ))}
      </ul>
      <button type="button" onClick={() => everywhere.mutate()}>
        Sign out everywhere else
      </button>{" "}
      <button type="button" onClick={() => signOut.mutate()}>
        Sign out
      </button>
    </section>
  );
}

export function ProfilePage() {
  const me = useMe();
  if (!me.data) return null;
  return (
    <main className="narrow">
      <h1>Your account</h1>
      <p>
        {me.data.email}, {me.data.role}
        {me.data.is_executor ? ", executor" : ""}
      </p>
      <NameForm me={me.data} />
      <section aria-labelledby="password-title">
        <h2 id="password-title">Password</h2>
        <ChangePasswordForm onDone={() => undefined} />
      </section>
      <Sessions />
    </main>
  );
}
