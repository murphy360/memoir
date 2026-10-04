import { useCallback, useState } from "react";

const PREFIX = "memoir:";

function read<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

/**
 * State kept in this browser's local storage: things that belong to a device, not to a
 * link (which microphone, which panels were open). Every key starts with "memoir:".
 */
export function useStoredState<T>(
  key: string,
  fallback: T,
): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => read(key, fallback));
  const set = useCallback(
    (next: T) => {
      setValue(next);
      try {
        window.localStorage.setItem(PREFIX + key, JSON.stringify(next));
      } catch {
        // Private browsing can refuse storage; the state still works for this visit.
      }
    },
    [key],
  );
  return [value, set];
}
