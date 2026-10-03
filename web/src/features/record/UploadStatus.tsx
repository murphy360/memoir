import { Link } from "react-router";

import { Button } from "../../components/Button";
import { clock, size } from "./format";
import type { Upload } from "./uploads";
import { uploads } from "./uploads";

/** Where one recording is, in plain words: uploading, being prepared, saved, or failed. */
export function describe(upload: Upload): string {
  switch (upload.state) {
    case "waiting":
      return "Waiting to upload";
    case "uploading":
      return `Uploading ${upload.bytes ? Math.round((upload.sent / upload.bytes) * 100) : 0}%`;
    case "processing":
      return "Saved. Preparing the audio";
    case "saved":
      return "Saved";
    case "failed":
      return `Not uploaded yet: ${upload.error ?? "something went wrong"}`;
  }
}

export function UploadStatus({ upload }: { upload: Upload }) {
  return (
    <div className={`upload upload-${upload.state}`}>
      <p role={upload.state === "failed" ? "alert" : "status"}>
        <strong>{describe(upload)}</strong>
        <span className="hint">
          {" "}
          {clock(upload.seconds)} · {size(upload.bytes)}
        </span>
      </p>
      {upload.state === "failed" ? (
        <div className="row">
          <Button
            variant="primary"
            onClick={() => void uploads.retry(upload.id)}
          >
            Try again
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              if (
                window.confirm(
                  "Delete this recording from this device? It was never uploaded.",
                )
              ) {
                void uploads.discard(upload.id);
              }
            }}
          >
            Delete it
          </Button>
        </div>
      ) : null}
      {(upload.state === "saved" || upload.state === "processing") &&
      upload.memoryId ? (
        <Link to={`/memories/${upload.memoryId}`}>Open the memory</Link>
      ) : null}
    </div>
  );
}

/** Recordings on this device that have not reached the server yet. */
export function PendingUploads({
  all,
  except,
}: {
  all: Upload[];
  except?: string;
}) {
  const items = all.filter((u) => u.id !== except && u.state !== "saved");
  if (!items.length) return null;
  return (
    <section aria-labelledby="pending-title" className="pending">
      <h2 id="pending-title">Recordings on this device</h2>
      {items.map((u) => (
        <UploadStatus key={u.id} upload={u} />
      ))}
    </section>
  );
}
