import type { InputHTMLAttributes, ReactNode } from "react";
import { useId } from "react";

import { messageOf } from "../lib/errors";

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: ReactNode;
};

/** A labelled input. The label is always visible: no placeholder-only fields. */
export function Field({ label, hint, ...input }: FieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} aria-describedby={hint ? hintId : undefined} {...input} />
      {hint ? (
        <p id={hintId} className="hint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** An error the user should read, announced to screen readers. */
export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  const message = typeof error === "string" ? error : messageOf(error);
  return (
    <p role="alert" className="error">
      {message}
    </p>
  );
}
