import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";

import { api, unwrap } from "../api/client";
import { ErrorText, Field } from "../components/Form";
import { ME, useMe } from "./useMe";

/** Where to go after signing in: the page that sent us here, never another site. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useMe();
  const signIn = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST("/api/auth/login", { body: { email, password } })),
    onSuccess: (user) => {
      queryClient.setQueryData(ME, user);
      navigate(safeNext(params.get("next")), { replace: true });
    },
  });

  if (me.data) return <Navigate to={safeNext(params.get("next"))} replace />;

  function submit(event: FormEvent) {
    event.preventDefault();
    signIn.mutate();
  }

  return (
    <main className="narrow">
      <h1>Sign in to Memoir</h1>
      <form onSubmit={submit}>
        <Field
          label="Email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <ErrorText error={signIn.error} />
        <button type="submit" className="primary" disabled={signIn.isPending}>
          {signIn.isPending ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="hint">
        Memoir is by invitation. Ask the family member who set it up for a link.
      </p>
    </main>
  );
}
