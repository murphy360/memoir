import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";

import { api, unwrap } from "../api/client";

type Props = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Whether to save a date Memoir cannot read, as text only. */
  keepTextOnly: boolean;
  onKeepTextOnlyChange: (keep: boolean) => void;
  hint?: string;
};

function useDebounced(value: string, ms: number) {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

/**
 * A free-text date with a live reading under it: "Reads as Summer 1968", or a plain
 * warning with examples and the choice to save it as written.
 */
export function DateField({
  label,
  value,
  onChange,
  keepTextOnly,
  onKeepTextOnlyChange,
  hint = "Any way you would say it: July 16, 1968; summer 1968; the 1960s; 1998 to 2002.",
}: Props) {
  const id = useId();
  const text = useDebounced(value.trim(), 300);
  const reading = useQuery({
    queryKey: ["date-reading", text],
    queryFn: async () =>
      unwrap(await api.POST("/api/dates/parse", { body: { text } })),
    enabled: text.length > 0,
    staleTime: Infinity,
  });
  const result = text ? reading.data : undefined;

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-describedby={`${id}-reading`}
      />
      <p id={`${id}-reading`} className="hint" aria-live="polite">
        {!text ? hint : null}
        {result?.ok ? `Reads as ${result.reading}` : null}
      </p>
      {result && !result.ok ? (
        <div role="alert" className="warning">
          <p>Memoir cannot read this date, so it cannot place it in time.</p>
          <p className="hint">Try: {result.examples.slice(0, 5).join("; ")}.</p>
          <label>
            <input
              type="checkbox"
              checked={keepTextOnly}
              onChange={(e) => onKeepTextOnlyChange(e.target.checked)}
            />{" "}
            Save it as written anyway
          </label>
        </div>
      ) : null}
    </div>
  );
}
