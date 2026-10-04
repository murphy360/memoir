import "fake-indexeddb/auto";

import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { fakeApi, ok, OWNER } from "./fakeApi";
import { PHONE, renderApp } from "./renderApp";

afterEach(() => vi.unstubAllGlobals());

const SILENT = {
  id: 7,
  title: null,
  transcript: "",
  transcript_state: "empty",
  extraction_state: null,
  audio_state: "normalised",
  response_to_question_id: null,
};
const PLACEMENT = { saved_to: null, suggestions: [], recent: [], nearby: [] };

test("a memory with nothing heard says so and can be deleted", async () => {
  const { calls } = fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/memories/7": ok(SILENT),
    "GET /api/memories/7/placement": ok(PLACEMENT),
    "GET /api/questions": ok({ items: [], next_cursor: null }),
    "DELETE /api/memories/7": () => new Response(null, { status: 204 }),
    "GET /api/questions/next": ok({ question: null, waiting: false }),
  });
  const router = renderApp("/memories/7", PHONE);
  expect(
    await screen.findByText(/Memoir heard nothing in this recording/),
  ).toBeInTheDocument();
  expect(screen.queryByText("Waiting to be placed.")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Delete this memory" }));
  const dialog = await screen.findByRole("dialog");
  expect(
    within(dialog).getByText(/erased for good after 30 days/),
  ).toBeVisible();
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete it" }));
  await waitFor(() =>
    expect(calls.some((c) => c.method === "DELETE")).toBe(true),
  );
  expect(await screen.findByText("Memory deleted.")).toBeInTheDocument();
  await waitFor(() => expect(router.state.location.pathname).toBe("/"));
});

test("cancelling keeps the memory", async () => {
  const { calls } = fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/memories/7": ok({
      ...SILENT,
      transcript_state: "done",
      transcript: "We drove.",
    }),
    "GET /api/memories/7/placement": ok(PLACEMENT),
    "GET /api/questions": ok({ items: [], next_cursor: null }),
  });
  renderApp("/memories/7", PHONE);
  fireEvent.click(
    await screen.findByRole("button", { name: "Delete this memory" }),
  );
  fireEvent.click(
    within(await screen.findByRole("dialog")).getByRole("button", {
      name: "Cancel",
    }),
  );
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(calls.some((c) => c.method === "DELETE")).toBe(false);
});

test("waiting to be placed offers to delete what was never said", async () => {
  fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/inbox": ok({
      items: [{ memory: SILENT, suggestion: null }],
      next_cursor: null,
    }),
  });
  renderApp("/inbox", PHONE);
  expect(await screen.findByText("Nothing was heard.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Delete it" })).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Place it" }),
  ).not.toBeInTheDocument();
});

test("right after a silent take, the record screen offers to delete it", async () => {
  const { installMedia } = await import("./media");
  installMedia();
  let received = 0;
  const upload = () =>
    Response.json({
      id: "u1",
      received_bytes: received,
      status: "open",
      memory_id: null,
    });
  fakeApi({
    "GET /api/me": ok(OWNER),
    "POST /api/capture/uploads": () =>
      Response.json(
        { id: "u1", received_bytes: 0, status: "open", memory_id: null },
        { status: 201 },
      ),
    "GET /api/capture/uploads/u1": upload,
    "PUT /api/capture/uploads/u1": async (r) => {
      received += (await r.arrayBuffer()).byteLength;
      return upload();
    },
    "POST /api/capture/uploads/u1/finalize": ok({
      ...SILENT,
      audio_state: "normalised",
    }),
    "GET /api/memories/7": ok(SILENT),
    "GET /api/questions/next": ok({ question: null, waiting: false }),
    "DELETE /api/memories/7": () => new Response(null, { status: 204 }),
  });
  renderApp("/record?start=1&quick=1", PHONE);
  await new Promise((r) => setTimeout(r, 50));
  fireEvent.click(await screen.findByRole("button", { name: "Stop" }));
  expect(
    await screen.findByText(
      "Nothing was heard in that recording.",
      {},
      { timeout: 5000 },
    ),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Delete it" }));
  fireEvent.click(
    within(await screen.findByRole("dialog")).getByRole("button", {
      name: "Delete it",
    }),
  );
  expect(
    await screen.findByText("Deleted. Nothing was kept."),
  ).toBeInTheDocument();
}, 15_000);
