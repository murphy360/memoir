import { useSyncExternalStore } from "react";

/** Below this width the phone posture (capture first); at or above, the wide one (review). */
export const WIDE_FROM = 768;
const QUERY = `(min-width: ${WIDE_FROM}px)`;

export type Posture = "phone" | "wide";

function subscribe(notify: () => void) {
  const list = window.matchMedia(QUERY);
  list.addEventListener("change", notify);
  return () => list.removeEventListener("change", notify);
}

/** Which posture this screen is in. A layout choice only: every route exists in both. */
export function usePosture(): Posture {
  return useSyncExternalStore(
    subscribe,
    () => (window.matchMedia(QUERY).matches ? "wide" : "phone"),
    () => "phone",
  );
}
