/**
 * The upload queue: every recording goes here the moment Stop is tapped, and leaves only
 * when the server has made it a memory. Each one is kept in IndexedDB with how far its
 * upload got, so a closed tab, a dead battery or a dropped connection resumes exactly
 * where the server stopped (the server answers a wrong offset with the right one).
 */

import { api, apiBaseUrl, csrfToken, unwrap } from "../../api/client";
import { store } from "./idb";

export const CHUNK = 1024 * 1024;
const RETRIES = 3;

export type Context = {
  event_id?: number;
  period_id?: number;
  person_id?: number;
  question_id?: number;
  quick?: boolean;
};

export type State = "waiting" | "uploading" | "processing" | "saved" | "failed";

export type Upload = {
  id: string;
  createdAt: string;
  contentType: string;
  context: Context;
  bytes: number;
  seconds: number;
  uploadId?: string;
  sent: number;
  state: State;
  memoryId?: number;
  error?: string;
};

const META = (id: string) => `upload:${id}`;
const BLOB = (id: string) => `blob:${id}`;

/**
 * The recording's bytes as stored. An ArrayBuffer rather than a Blob: every browser keeps
 * one in IndexedDB (older Safari did not keep Blobs reliably).
 */
type Stored = { type: string; data: ArrayBuffer };

async function keep(id: string, blob: Blob): Promise<void> {
  await store.put(BLOB(id), {
    type: blob.type,
    data: await blob.arrayBuffer(),
  } satisfies Stored);
}

async function load(id: string): Promise<Blob | null> {
  const stored = await store.get<Stored>(BLOB(id));
  // byteLength, not instanceof: a buffer from IndexedDB may come from another realm.
  if (!stored?.data?.byteLength) return null;
  return new Blob([stored.data], { type: stored.type });
}

type Listener = (uploads: Upload[]) => void;

function base(): string {
  return apiBaseUrl(window.location.origin, import.meta.env.BASE_URL);
}

class Refused extends Error {
  constructor(
    readonly status: number,
    readonly body: { error?: { code?: string; message?: string } },
  ) {
    super(body.error?.message ?? `The server answered ${status}.`);
  }
}

async function putChunk(uploadId: string, offset: number, chunk: Blob) {
  const response = await fetch(
    `${base()}/api/capture/uploads/${uploadId}?offset=${offset}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-CSRF-Token": csrfToken() ?? "",
      },
      body: chunk,
      credentials: "same-origin",
    },
  );
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Refused(response.status, body);
  return body as { received_bytes: number };
}

export class UploadQueue {
  /** `backoffMs`: the first wait between retries (it doubles). Tests make it short. */
  constructor(private readonly backoffMs = 500) {}

  private uploads = new Map<string, Upload>();
  private listeners = new Set<Listener>();
  private running = new Set<string>();

  /** Load whatever an earlier visit left, and carry on with it. */
  async resume(): Promise<void> {
    const keys = (await store.keys())
      .map(String)
      .filter((k) => k.startsWith("upload:"));
    for (const key of keys) {
      const saved = await store.get<Upload>(key);
      if (saved && saved.state !== "saved") {
        this.uploads.set(saved.id, {
          ...saved,
          state: saved.state === "processing" ? "processing" : "waiting",
        });
      }
    }
    this.emit();
    await Promise.all([...this.uploads.keys()].map((id) => this.run(id)));
  }

  /** Keep a new recording safe, then start sending it. */
  async add(blob: Blob, context: Context, seconds: number): Promise<string> {
    const id = crypto.randomUUID();
    const upload: Upload = {
      id,
      createdAt: new Date().toISOString(),
      contentType: blob.type || "audio/webm",
      context,
      bytes: blob.size,
      seconds,
      sent: 0,
      state: "waiting",
    };
    await keep(id, blob);
    await this.save(upload);
    void this.run(id);
    return id;
  }

  get(id: string): Upload | undefined {
    return this.uploads.get(id);
  }

  list(): Upload[] {
    return [...this.uploads.values()].sort((a, b) =>
      a.createdAt.localeCompare(b.createdAt),
    );
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  retry(id: string): Promise<void> {
    const upload = this.uploads.get(id);
    if (upload?.state === "failed") return this.run(id);
    return Promise.resolve();
  }

  /** Give up on a recording that will not upload: it is deleted from this device. */
  async discard(id: string): Promise<void> {
    this.uploads.delete(id);
    await store.remove(META(id));
    await store.remove(BLOB(id));
    this.emit();
  }

  async run(id: string): Promise<void> {
    if (this.running.has(id)) return;
    this.running.add(id);
    try {
      for (let attempt = 1; ; attempt++) {
        try {
          await this.step(id);
          return;
        } catch (error) {
          if (
            attempt >= RETRIES ||
            (error instanceof Refused &&
              error.status < 500 &&
              error.status !== 409)
          ) {
            await this.patch(id, {
              state: "failed",
              error: (error as Error).message,
            });
            return;
          }
          await new Promise((r) =>
            setTimeout(r, this.backoffMs * 2 ** attempt),
          );
        }
      }
    } finally {
      this.running.delete(id);
    }
  }

  private async step(id: string): Promise<void> {
    let upload = this.uploads.get(id);
    if (!upload) return;
    if (upload.state !== "processing") {
      const blob = await load(id);
      if (!blob) throw new Error("The recording is no longer on this device.");
      upload = await this.send(upload, blob);
      const memory = unwrap(
        await api.POST("/api/capture/uploads/{upload_id}/finalize", {
          params: { path: { upload_id: upload.uploadId! } },
        }),
      );
      await store.remove(BLOB(id));
      upload = await this.patch(id, {
        state: "processing",
        memoryId: memory.id,
        error: undefined,
      });
    }
    await this.untilProcessed(upload);
  }

  private async send(upload: Upload, blob: Blob): Promise<Upload> {
    let current = await this.patch(upload.id, {
      state: "uploading",
      error: undefined,
    });
    if (!current.uploadId) {
      const opened = unwrap(
        await api.POST("/api/capture/uploads", {
          body: {
            content_type: current.contentType,
            context: { quick: false, ...current.context },
          },
        }),
      );
      current = await this.patch(upload.id, { uploadId: opened.id, sent: 0 });
    } else {
      const state = unwrap(
        await api.GET("/api/capture/uploads/{upload_id}", {
          params: { path: { upload_id: current.uploadId } },
        }),
      );
      current = await this.patch(upload.id, { sent: state.received_bytes });
    }
    while (current.sent < blob.size) {
      const chunk = blob.slice(current.sent, current.sent + CHUNK);
      try {
        const answer = await putChunk(current.uploadId!, current.sent, chunk);
        current = await this.patch(upload.id, { sent: answer.received_bytes });
      } catch (error) {
        if (!(
          error instanceof Refused && error.body.error?.code === "wrong_offset"
        ))
          throw error;
        const state = unwrap(
          await api.GET("/api/capture/uploads/{upload_id}", {
            params: { path: { upload_id: current.uploadId! } },
          }),
        );
        current = await this.patch(upload.id, { sent: state.received_bytes });
      }
    }
    return current;
  }

  /** The server is normalising the recording; it is safe, so this only updates the label. */
  private async untilProcessed(upload: Upload): Promise<void> {
    for (let i = 0; i < 120; i++) {
      const memory = unwrap(
        await api.GET("/api/memories/{memory_id}", {
          params: { path: { memory_id: upload.memoryId! } },
        }),
      );
      if (memory.audio_state !== "normalising") break;
      await new Promise((r) => setTimeout(r, this.backoffMs * 2));
    }
    await this.patch(upload.id, { state: "saved" });
    await store.remove(META(upload.id));
  }

  private async patch(id: string, change: Partial<Upload>): Promise<Upload> {
    const next = { ...this.uploads.get(id)!, ...change };
    await this.save(next);
    return next;
  }

  private async save(upload: Upload): Promise<void> {
    this.uploads.set(upload.id, upload);
    await store.put(META(upload.id), upload);
    this.emit();
  }

  private emit() {
    const all = this.list();
    this.listeners.forEach((l) => l(all));
  }
}

/** The one queue for this tab. */
export const uploads = new UploadQueue();
