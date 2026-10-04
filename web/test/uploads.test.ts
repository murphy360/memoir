import "fake-indexeddb/auto";

import { CHUNK, UploadQueue } from "../src/features/record/uploads";

type Call = { method: string; path: string; offset: number | null };

/**
 * A small capture server: it keeps the bytes it received, refuses a wrong offset with the
 * right one, and can drop the connection after a number of chunks.
 */
function server(options: { dropAfter?: number } = {}) {
  let received = 0;
  let chunks = 0;
  const calls: Call[] = [];
  const fetch = vi.fn(async (input: Request | string, init?: RequestInit) => {
    const request =
      typeof input === "string" ? new Request(input, init) : input;
    const url = new URL(request.url);
    const path = url.pathname.replace(/^\/memoir/, "");
    const offset = url.searchParams.has("offset")
      ? Number(url.searchParams.get("offset"))
      : null;
    calls.push({ method: request.method, path, offset });
    const state = () => ({
      id: "u1",
      received_bytes: received,
      status: "open",
      memory_id: null,
    });
    if (request.method === "POST" && path === "/api/capture/uploads")
      return Response.json(state(), { status: 201 });
    if (request.method === "GET" && path === "/api/capture/uploads/u1")
      return Response.json(state());
    if (request.method === "PUT") {
      if (options.dropAfter !== undefined && chunks >= options.dropAfter)
        throw new TypeError("Failed to fetch");
      const body = await request.arrayBuffer();
      if (offset !== received) {
        return Response.json(
          { error: { code: "wrong_offset", message: "continue" } },
          { status: 409 },
        );
      }
      received += body.byteLength;
      chunks += 1;
      return Response.json(state());
    }
    if (path === "/api/capture/uploads/u1/finalize")
      return Response.json({ id: 42, audio_state: "normalising" });
    if (path === "/api/memories/42")
      return Response.json({ id: 42, audio_state: "normalised" });
    return Response.json({}, { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return {
    calls,
    received: () => received,
    heal: () => {
      options.dropAfter = undefined;
    },
  };
}

afterEach(() => vi.unstubAllGlobals());

const recording = () =>
  new Blob([new Uint8Array(Math.round(CHUNK * 2.5))], { type: "audio/webm" });

test("a recording uploads in chunks, then is saved", async () => {
  const s = server();
  const queue = new UploadQueue(1);
  const id = await queue.add(recording(), { quick: true }, 12);
  await vi.waitFor(() => expect(queue.get(id)?.state).toBe("saved"), {
    timeout: 3000,
  });
  expect(
    s.calls.filter((c) => c.method === "PUT").map((c) => c.offset),
  ).toEqual([0, CHUNK, 2 * CHUNK]);
  expect(queue.get(id)?.memoryId).toBe(42);
});

test("after the browser is closed mid-upload, the next visit resumes from the server's offset", async () => {
  const s = server({ dropAfter: 1 });
  const first = new UploadQueue(1);
  const id = await first.add(recording(), { event_id: 9 }, 30);
  await vi.waitFor(() => expect(first.get(id)?.state).toBe("failed"), {
    timeout: 3000,
  });
  expect(s.received()).toBe(CHUNK);

  // A new visit: a fresh queue reads what the last one left in IndexedDB.
  s.heal();
  const second = new UploadQueue(1);
  await second.resume();
  await vi.waitFor(() => expect(second.get(id)?.state).toBe("saved"), {
    timeout: 3000,
  });
  const puts = s.calls.filter((c) => c.method === "PUT" && c.offset !== null);
  expect(puts.at(-2)?.offset).toBe(CHUNK);
  expect(puts.at(-1)?.offset).toBe(2 * CHUNK);
  expect(
    s.calls.filter(
      (c) => c.method === "POST" && c.path === "/api/capture/uploads",
    ),
  ).toHaveLength(1);
});

test("a failed upload waits on the device until retried", async () => {
  const s = server({ dropAfter: 0 });
  const queue = new UploadQueue(1);
  const id = await queue.add(recording(), {}, 5);
  await vi.waitFor(() => expect(queue.get(id)?.state).toBe("failed"), {
    timeout: 3000,
  });
  expect(queue.get(id)?.error).toBe("Failed to fetch");
  s.heal();
  await queue.retry(id);
  await vi.waitFor(() => expect(queue.get(id)?.state).toBe("saved"), {
    timeout: 3000,
  });
});

test("a discarded recording leaves the device", async () => {
  server({ dropAfter: 0 });
  const queue = new UploadQueue(1);
  const id = await queue.add(recording(), {}, 5);
  await vi.waitFor(() => expect(queue.get(id)?.state).toBe("failed"), {
    timeout: 3000,
  });
  await queue.discard(id);
  const again = new UploadQueue(1);
  await again.resume();
  expect(again.get(id)).toBeUndefined();
});
