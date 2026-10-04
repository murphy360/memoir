import { fireEvent, screen, waitFor } from "@testing-library/react";

import { fail, fakeApi, ok, OWNER } from "./fakeApi";
import { renderApp, WIDE } from "./renderApp";

const BASE = {
  id: 5,
  title: "Driving to Erie with my brother Jim",
  description: "Corey and Jim drove to Erie.",
  date_text: "summer of 1968",
  transcript: "My name is Corey.",
  transcript_state: "done",
  extraction_state: "done",
  audio_state: "normalised",
  audio_seconds: 3,
};

afterEach(() => vi.unstubAllGlobals());

test("a memory shows its recording, its words and its title", async () => {
  fakeApi({ "GET /api/me": ok(OWNER), "GET /api/memories/5": ok(BASE) });
  renderApp("/memories/5", WIDE);
  expect(
    await screen.findByRole("heading", { name: BASE.title }),
  ).toBeInTheDocument();
  expect(screen.getByText("My name is Corey.")).toBeInTheDocument();
  expect(document.querySelector("audio")?.getAttribute("src")).toMatch(
    /\/api\/memories\/5\/audio$/,
  );
});

test("while transcribing it says so", async () => {
  fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/memories/5": ok({
      ...BASE,
      transcript: null,
      transcript_state: "transcribing",
      title: null,
    }),
  });
  renderApp("/memories/5");
  expect(await screen.findByText(/Writing down the words/)).toBeInTheDocument();
});

test("with AI off it says the recording is safe and can run later", async () => {
  const { calls } = fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/memories/5": ok({
      ...BASE,
      transcript: null,
      transcript_state: "ai_off",
    }),
    "POST /api/memories/5/transcribe": ok({
      ...BASE,
      transcript: null,
      transcript_state: "transcribing",
    }),
  });
  renderApp("/memories/5");
  expect(await screen.findByText(/AI is off/)).toHaveTextContent(
    "The recording is safe.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Write them down now" }));
  expect(await screen.findByText(/Writing down the words/)).toBeInTheDocument();
  expect(calls.some((c) => c.method === "POST")).toBe(true);
});

test("a failed transcription offers to try again", async () => {
  fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/memories/5": ok({
      ...BASE,
      transcript: null,
      transcript_state: "failed",
      analysis_error: "Gemini answered 402: credits are depleted",
    }),
  });
  renderApp("/memories/5");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The recording is safe.",
  );
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  expect(
    screen.getByText("Gemini answered 402: credits are depleted"),
  ).toBeInTheDocument();
});

test("the words can be corrected", async () => {
  const { calls } = fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/memories/5": ok(BASE),
    "PATCH /api/memories/5": ok({
      ...BASE,
      transcript: "My name is Corey Murphy.",
    }),
  });
  renderApp("/memories/5", WIDE);
  fireEvent.click(
    await screen.findByRole("button", { name: "Correct the words" }),
  );
  fireEvent.change(screen.getByLabelText("The words"), {
    target: { value: "My name is Corey Murphy." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save the words" }));
  // Saving re-mounts the words (they are keyed on their text): look up the current one.
  await waitFor(() =>
    expect(screen.getByText("My name is Corey Murphy.")).toBeInTheDocument(),
  );
  await waitFor(() =>
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({
      transcript: "My name is Corey Murphy.",
    }),
  );
  expect(
    await screen.findByText(/Memoir will not change them/),
  ).toBeInTheDocument();
});

test("a memory that is not there says so", async () => {
  fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/memories/9": fail(404, "not_found", "No such memory."),
  });
  renderApp("/memories/9");
  expect(await screen.findByRole("alert")).toHaveTextContent("No such memory.");
});
