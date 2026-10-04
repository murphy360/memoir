import { useEffect, useRef, useState } from "react";

import { Button } from "../../components/Button";
import { useToast } from "../../components/Toast";
import { useStoredState } from "../../lib/storedState";
import { Advanced, DEVICE_KEY } from "./Advanced";
import { useContextLabel, useRecordContext } from "./context";
import { clock, size } from "./format";
import { Level } from "./Level";
import { TakePlayer } from "./TakePlayer";
import { PendingUploads, UploadStatus } from "./UploadStatus";
import { uploads } from "./uploads";
import { useRecorder } from "./useRecorder";
import { useUploads } from "./useUploads";

/**
 * Record a memory. Opened with ?start=1 it begins at once, so from the home screen a
 * recording is one tap to start and one to stop. Stop is always on screen while
 * recording. The take is kept on this device until the server has it.
 */
export function RecordScreen() {
  const { context, autostart } = useRecordContext();
  const label = useContextLabel(context);
  const [device] = useStoredState<string>(DEVICE_KEY, "");
  const recorder = useRecorder();
  const toast = useToast();
  const all = useUploads();
  const [uploadId, setUploadId] = useState<string | null>(null);
  const begun = useRef(false);

  useEffect(() => {
    if (autostart && !begun.current) {
      begun.current = true;
      void recorder.start(device || undefined);
    }
  }, [autostart, device, recorder]);

  async function stop() {
    const take = await recorder.stop();
    if (take) setUploadId(await uploads.add(take.blob, context, take.seconds));
  }

  function cancel() {
    recorder.cancel();
    toast("Recording discarded. Nothing was saved.");
  }

  const current = all.find((u) => u.id === uploadId);
  const { state } = recorder;

  return (
    <section aria-labelledby="record-title" className="record">
      <h1 id="record-title">Record a memory</h1>
      {label ? <p className="context">{label}</p> : null}

      {state === "recording" ? (
        <div className="recording">
          <p className="elapsed" aria-live="off">
            <span className="dot" aria-hidden="true" /> Recording{" "}
            {clock(recorder.seconds)}
          </p>
          <Level level={recorder.level} />
          <Button
            variant="primary"
            className="button primary big"
            onClick={() => void stop()}
          >
            Stop
          </Button>
          <Button onClick={cancel}>Cancel</Button>
        </div>
      ) : null}

      {state === "starting" ? (
        <p role="status">Opening the microphone…</p>
      ) : null}

      {state === "idle" || state === "error" || state === "stopped" ? (
        <>
          {recorder.error ? <p role="alert">{recorder.error}</p> : null}
          {state === "stopped" && recorder.take ? (
            <div className="take">
              <TakePlayer src={recorder.take.url} />
              {current ? (
                <UploadStatus upload={current} />
              ) : (
                <p className="hint">
                  {clock(recorder.take.seconds)} ·{" "}
                  {size(recorder.take.blob.size)}
                </p>
              )}
            </div>
          ) : null}
          <Button
            variant="primary"
            className="button primary big"
            onClick={() => void recorder.start(device || undefined)}
          >
            {state === "stopped" ? "Record another" : "Start recording"}
          </Button>
          <Advanced />
        </>
      ) : null}

      <PendingUploads all={all} except={uploadId ?? undefined} />
    </section>
  );
}
