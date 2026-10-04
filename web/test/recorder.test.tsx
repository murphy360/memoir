import "fake-indexeddb/auto";

import {
  act,
  fireEvent,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

import { useRecorder } from "../src/features/record/useRecorder";
import { fakeApi, ok, OWNER } from "./fakeApi";
import { installMedia } from "./media";
import { PHONE, renderApp, WIDE } from "./renderApp";

afterEach(() => vi.unstubAllGlobals());

test("the recorder goes idle, recording, stopped, and keeps the take", async () => {
  const { track } = installMedia();
  const { result } = renderHook(() => useRecorder());
  expect(result.current.state).toBe("idle");
  await act(() => result.current.start());
  expect(result.current.state).toBe("recording");
  expect(result.current.level).toBeGreaterThan(0);
  await act(() => new Promise((r) => setTimeout(r, 60)));
  let take: Awaited<ReturnType<typeof result.current.stop>> = null;
  await act(async () => {
    take = await result.current.stop();
  });
  expect(result.current.state).toBe("stopped");
  expect(take!.blob.size).toBeGreaterThan(10);
  expect(take!.blob.type).toBe("audio/webm;codecs=opus");
  expect(track.stop).toHaveBeenCalled();
});

test("cancelling keeps nothing and frees the microphone", async () => {
  const { track } = installMedia();
  const { result } = renderHook(() => useRecorder());
  await act(() => result.current.start());
  act(() => result.current.cancel());
  expect(result.current.state).toBe("idle");
  expect(result.current.take).toBeNull();
  expect(track.stop).toHaveBeenCalled();
});

test("a refused microphone says why", async () => {
  installMedia({ deny: true });
  const { result } = renderHook(() => useRecorder());
  await act(() => result.current.start());
  expect(result.current.state).toBe("error");
  expect(result.current.error).toBe(
    "Memoir needs your permission to use the microphone.",
  );
});

const LABELS = {
  "GET /api/events/9": ok({ id: 9, title: "The wedding", participants: [] }),
  "GET /api/people/7": ok({ id: 7, name: "Grandma", aliases: [] }),
  "GET /api/periods/3": ok({ id: 3, title: "Navy years" }),
  "GET /api/questions/5": ok({ id: 5, text: "Which brother drove?" }),
};

describe.each([
  ["home", "/record?start=1&quick=1", null],
  ["an event", "/record?start=1&event=9", "Adding to: The wedding"],
  ["a person", "/record?start=1&person=7", "A memory about: Grandma"],
  ["a period", "/record?start=1&period=3", "A memory in: Navy years"],
  [
    "a question",
    "/record?start=1&question=5",
    "Answering: Which brother drove?",
  ],
])("started from %s", (_, path, label) => {
  test.each([
    ["phone", PHONE],
    ["wide", WIDE],
  ])("Stop is on screen while recording (%s)", async (_posture, width) => {
    installMedia();
    fakeApi({ "GET /api/me": ok(OWNER), ...LABELS });
    renderApp(path, width);
    expect(await screen.findByRole("button", { name: "Stop" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeVisible();
    expect(
      screen.getByRole("meter", { name: "Input level" }),
    ).toBeInTheDocument();
    if (label) expect(await screen.findByText(label)).toBeInTheDocument();
  });
});

test("one tap from home starts recording", async () => {
  installMedia();
  fakeApi({ "GET /api/me": ok(OWNER) });
  renderApp("/", PHONE);
  fireEvent.click(await screen.findByRole("link", { name: "Record a memory" }));
  expect(
    await screen.findByRole("button", { name: "Stop" }),
  ).toBeInTheDocument();
});

test("the header's Record starts recording on a wide screen", async () => {
  installMedia();
  fakeApi({ "GET /api/me": ok(OWNER) });
  renderApp("/people", WIDE);
  fireEvent.click(
    within(await screen.findByRole("banner")).getByRole("link", {
      name: "Record",
    }),
  );
  expect(
    await screen.findByRole("button", { name: "Stop" }),
  ).toBeInTheDocument();
});

test("cancel says the recording was discarded", async () => {
  installMedia();
  fakeApi({ "GET /api/me": ok(OWNER) });
  renderApp("/record?start=1", PHONE);
  fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
  expect(
    await screen.findByText("Recording discarded. Nothing was saved."),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Start recording" }),
  ).toBeInTheDocument();
});

test("after Stop the take plays at once and its upload is shown", async () => {
  installMedia();
  fakeApi({
    "GET /api/me": ok(OWNER),
    "POST /api/capture/uploads": ok(
      { id: "u1", received_bytes: 0, status: "open", memory_id: null },
      201,
    ),
    "PUT /api/capture/uploads/u1": ok({
      id: "u1",
      received_bytes: 999,
      status: "open",
      memory_id: null,
    }),
  });
  renderApp("/record?start=1", PHONE);
  await new Promise((r) => setTimeout(r, 50));
  fireEvent.click(await screen.findByRole("button", { name: "Stop" }));
  expect(
    await screen.findByRole("button", { name: "Record another memory" }),
  ).toBeInTheDocument();
  expect(document.querySelector("audio")).toHaveAttribute("src", "blob:take");
  await waitFor(() =>
    expect(
      screen.getByText(/Uploading|Waiting to upload|Not uploaded yet/),
    ).toBeInTheDocument(),
  );
});
