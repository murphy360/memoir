import { useCallback } from "react";
import { useSearchParams } from "react-router";

/**
 * A piece of state kept in the URL's query string, so a reload or a shared link lands on
 * the same view. Writing replaces the history entry: typing in a search box does not
 * fill the back button.
 */
export function useUrlState(
  key: string,
  fallback = "",
): [string, (value: string) => void] {
  const [params, setParams] = useSearchParams();
  const value = params.get(key) ?? fallback;
  const set = useCallback(
    (next: string) => {
      setParams(
        (current) => {
          const updated = new URLSearchParams(current);
          if (next === fallback || next === "") updated.delete(key);
          else updated.set(key, next);
          return updated;
        },
        { replace: true },
      );
    },
    [key, fallback, setParams],
  );
  return [value, set];
}
