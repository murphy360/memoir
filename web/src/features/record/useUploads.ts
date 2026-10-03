import { useEffect, useSyncExternalStore } from "react";

import { uploads, type Upload } from "./uploads";

let snapshot: Upload[] = [];
uploads.subscribe((all) => {
  snapshot = all;
});

/** The upload queue, as React state. */
export function useUploads(): Upload[] {
  return useSyncExternalStore(
    (notify) => uploads.subscribe(notify),
    () => snapshot,
    () => snapshot,
  );
}

let resumed = false;

/** Mounted once in the shell: carry on with uploads an earlier visit left unfinished. */
export function useResumeUploads() {
  useEffect(() => {
    if (resumed) return;
    resumed = true;
    uploads.resume().catch(() => undefined);
  }, []);
}
