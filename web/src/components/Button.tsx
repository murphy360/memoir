import type { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  busy?: boolean;
};

/** A real button: keyboard-reachable, labelled, and disabled while busy. */
export function Button({
  variant = "secondary",
  busy,
  children,
  ...rest
}: Props) {
  return (
    <button
      type="button"
      className={`button ${variant}`}
      aria-busy={busy || undefined}
      disabled={busy || rest.disabled}
      {...rest}
    >
      {children}
    </button>
  );
}
