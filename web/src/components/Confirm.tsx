import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "./Button";

type Ask = { title: string; body: string; confirm: string; danger?: boolean };

/**
 * A confirmation that says, in plain words, what will happen. Returns a function that
 * opens it and resolves true or false, and the dialog to render.
 */
export function useConfirm() {
  const [ask, setAsk] = useState<Ask | null>(null);
  const resolver = useRef<(ok: boolean) => void>(() => undefined);
  const dialog = useRef<HTMLDialogElement>(null);

  const confirm = useCallback((next: Ask) => {
    setAsk(next);
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
    });
  }, []);

  useEffect(() => {
    const el = dialog.current;
    if (ask && el && !el.open) {
      if (typeof el.showModal === "function") el.showModal();
      else el.setAttribute("open", "");
    }
  }, [ask]);

  const close = (ok: boolean) => {
    dialog.current?.close?.();
    dialog.current?.removeAttribute("open");
    setAsk(null);
    resolver.current(ok);
  };

  const element = ask ? (
    <dialog
      ref={dialog}
      className="confirm"
      aria-labelledby="confirm-title"
      onCancel={() => close(false)}
    >
      <h2 id="confirm-title">{ask.title}</h2>
      <p>{ask.body}</p>
      <div className="actions">
        <Button onClick={() => close(false)}>Cancel</Button>
        <Button
          variant={ask.danger ? "danger" : "primary"}
          onClick={() => close(true)}
        >
          {ask.confirm}
        </Button>
      </div>
    </dialog>
  ) : null;

  return { confirm, element };
}
