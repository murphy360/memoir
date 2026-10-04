import "fake-indexeddb/auto";

import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { fakeApi, ok, OWNER } from "./fakeApi";
import { installMedia } from "./media";
import { PHONE, renderApp, WIDE } from "./renderApp";

afterEach(() => vi.unstubAllGlobals());

const question = (id: number, text: string, extra = {}) => ({
  id,
  text,
  status: "pending",
  scope: "general",
  source_memory_id: null,
  event_id: null,
  period_id: null,
  person_id: null,
  answered_by_memory_id: null,
  asked_of_id: null,
  about: null,
  ...extra,
});
const CALL = question(1, "What should we call you?");
const BORN = question(2, "Where and when were you born?");
const SEEDS = [CALL, BORN, question(3, "Tell me about your parents.")];

test("home shows the next question with one Record button", async () => {
  fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/questions/next": ok({
      question: question(9, "You said your brother drove. Which brother?", {
        about: "Driving to Erie",
      }),
      waiting: false,
    }),
  });
  renderApp("/", PHONE);
  const card = await screen.findByRole("region", {
    name: "A question for you",
  });
  expect(
    within(card).getByText("You said your brother drove. Which brother?"),
  ).toBeInTheDocument();
  expect(within(card).getByText("About: Driving to Erie")).toBeInTheDocument();
  expect(
    within(card).getByRole("link", { name: "Record your answer" }),
  ).toHaveAttribute("href", "/record?start=1&question=9");
});

test("the wide home shows the question too", async () => {
  fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/questions/next": ok({ question: CALL, waiting: false }),
  });
  renderApp("/", WIDE);
  expect(
    await screen.findByText("What should we call you?"),
  ).toBeInTheDocument();
});

test("an empty archive's questions are the three seeds, and dismissing is for good", async () => {
  let items = SEEDS;
  const { calls } = fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/questions/for-you": () => Response.json({ items }),
    "PATCH /api/questions/2": () => {
      items = items.filter((q) => q.id !== 2);
      return Response.json({ ...BORN, status: "dismissed" });
    },
  });
  renderApp("/questions", PHONE);
  for (const q of SEEDS)
    expect(await screen.findByText(q.text)).toBeInTheDocument();
  const born = screen.getByText(BORN.text).closest("li")!;
  fireEvent.click(
    within(born as HTMLElement).getByRole("button", {
      name: "Don't ask this again",
    }),
  );
  await waitFor(() =>
    expect(screen.queryByText(BORN.text)).not.toBeInTheDocument(),
  );
  expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
    status: "dismissed",
  });
  expect(
    await screen.findByText("Memoir will not ask that again."),
  ).toBeInTheDocument();
});

test("with nothing waiting the list says how questions come", async () => {
  fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/questions/for-you": ok({ items: [] }),
  });
  renderApp("/questions", WIDE);
  expect(await screen.findByText("No questions waiting")).toBeInTheDocument();
});

test("a memory shows the question it answered and the ones it raised", async () => {
  fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/memories/5": ok({
      id: 5,
      title: "Jim's Ford",
      response_to_question_id: 9,
      transcript_state: "done",
      extraction_state: "done",
      audio_state: null,
    }),
    "GET /api/memories/5/placement": ok({
      saved_to: null,
      suggestions: [],
      recent: [],
      nearby: [],
    }),
    "GET /api/questions/9": ok(question(9, "Which brother drove?")),
    "GET /api/questions": ok({
      items: [question(10, "What colour was the Ford?")],
      next_cursor: null,
    }),
  });
  renderApp("/memories/5", PHONE);
  expect(await screen.findByText("Which brother drove?")).toBeInTheDocument();
  const raised = await screen.findByRole("region", {
    name: "Questions this raised",
  });
  expect(
    within(raised).getByRole("link", { name: "Record your answer" }),
  ).toHaveAttribute("href", "/record?start=1&question=10");
});

/** The server side of three recordings: uploads, memories, and the next questions. */
function interviewApi() {
  const next: Record<number, ReturnType<typeof question> | null> = {
    101: question(2, "You said your brother drove. Which brother?"),
    102: question(3, "What car was it?"),
    103: null,
  };
  let waited = false;
  let received = 0;
  const routes: Record<string, (r: Request) => Response | Promise<Response>> = {
    "GET /api/me": ok(OWNER),
    "GET /api/questions/1": ok(CALL),
    "GET /api/questions/2": ok(next[101]),
    "GET /api/questions/3": ok(next[102]),
    "GET /api/questions/next": (r) => {
      const after = Number(new URL(r.url).searchParams.get("after_memory_id"));
      if (!after) return Response.json({ question: CALL, waiting: false });
      if (after === 101 && !waited) {
        waited = true;
        return Response.json({ question: null, waiting: true });
      }
      return Response.json({ question: next[after], waiting: false });
    },
  };
  for (const n of [1, 2, 3]) {
    const memoryId = 100 + n;
    routes["POST /api/capture/uploads"] = async (r) => {
      received = 0;
      const body = (await r.clone().json()) as {
        context: { question_id: number };
      };
      const id = `u${body.context.question_id}`;
      return Response.json(
        { id, received_bytes: 0, status: "open", memory_id: null },
        { status: 201 },
      );
    };
    routes[`GET /api/capture/uploads/u${n}`] = () =>
      Response.json({
        id: `u${n}`,
        received_bytes: received,
        status: "open",
        memory_id: null,
      });
    routes[`PUT /api/capture/uploads/u${n}`] = async (r) => {
      received += (await r.arrayBuffer()).byteLength;
      return Response.json({
        id: `u${n}`,
        received_bytes: received,
        status: "open",
        memory_id: null,
      });
    };
    routes[`POST /api/capture/uploads/u${n}/finalize`] = ok({
      id: memoryId,
      audio_state: "normalised",
    });
    routes[`GET /api/memories/${memoryId}`] = ok({
      id: memoryId,
      audio_state: "normalised",
    });
    routes[`GET /api/memories/${memoryId}/placement`] = ok({
      saved_to: null,
      suggestions: [],
      recent: [],
      nearby: [],
    });
  }
  return fakeApi(routes);
}

test("the loop: each answer is Record and Stop, and the next question follows", async () => {
  installMedia();
  const { calls } = interviewApi();
  renderApp("/", PHONE);
  fireEvent.click(
    await screen.findByRole("link", { name: "Record your answer" }),
  );
  const asked = [
    "What should we call you?",
    "You said your brother drove. Which brother?",
    "What car was it?",
  ];
  for (const [n, text] of asked.entries()) {
    expect(await screen.findByText(`Answering: ${text}`)).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 50));
    fireEvent.click(await screen.findByRole("button", { name: "Stop" }));
    if (n === 0)
      expect(
        await screen.findByText(
          "Thinking of a question about what you said…",
          {},
          { timeout: 5000 },
        ),
      ).toBeInTheDocument();
    if (n < asked.length - 1) {
      expect(
        await screen.findByText(asked[n + 1]!, {}, { timeout: 5000 }),
      ).toBeInTheDocument();
      fireEvent.click(screen.getByRole("link", { name: "Record your answer" }));
    }
  }
  expect(
    await screen.findByText(
      "No more questions for now. Thank you, every word is saved.",
    ),
  ).toBeInTheDocument();
  const opened = calls.filter(
    (c) => c.method === "POST" && c.path === "/api/capture/uploads",
  );
  expect(opened.map((c) => (c.body as { context: object }).context)).toEqual([
    { question_id: 1, quick: false },
    { question_id: 2, quick: false },
    { question_id: 3, quick: false },
  ]);
}, 20_000);
