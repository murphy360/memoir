import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { api, unwrap } from "../api/client";
import { ErrorText, Field } from "../components/Form";
import { ME, useMe } from "./useMe";

const RULE = "At least 12 characters. A few words you will remember work well.";

/** Change your password; also where a temporary password from the owner lands you. */
export function ChangePasswordForm({ onDone }: { onDone: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [mismatch, setMismatch] = useState(false);
  const queryClient = useQueryClient();
  const change = useMutation({
    mutationFn: async () => {
      const result = await api.POST("/api/me/password", {
        body: { current_password: current, new_password: next },
      });
      if (result.error !== undefined) unwrap(result);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ME });
      onDone();
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setMismatch(next !== again);
    if (next === again) change.mutate();
  }

  return (
    <form onSubmit={submit}>
      <Field
        label="Current password"
        type="password"
        autoComplete="current-password"
        required
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
      />
      <Field
        label="New password"
        type="password"
        autoComplete="new-password"
        required
        minLength={12}
        hint={RULE}
        value={next}
        onChange={(e) => setNext(e.target.value)}
      />
      <Field
        label="New password again"
        type="password"
        autoComplete="new-password"
        required
        value={again}
        onChange={(e) => setAgain(e.target.value)}
      />
      <ErrorText
        error={mismatch ? "The two new passwords differ." : change.error}
      />
      <button type="submit" className="primary" disabled={change.isPending}>
        Change password
      </button>
    </form>
  );
}

export function ChangePasswordPage() {
  const me = useMe();
  const navigate = useNavigate();
  return (
    <main className="narrow">
      <h1>Choose a new password</h1>
      {me.data?.must_change_password ? (
        <p>
          You signed in with a temporary password. Pick one of your own to
          continue.
        </p>
      ) : null}
      <ChangePasswordForm onDone={() => navigate("/", { replace: true })} />
    </main>
  );
}
