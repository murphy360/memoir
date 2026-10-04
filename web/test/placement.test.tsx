import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { fakeApi, ok, OWNER } from "./fakeApi";
import { PHONE, renderApp, WIDE } from "./renderApp";

const MEMORY = {
  id: 5,
  title: "Corn dogs at the fair",
  date_text: "August 1968",
  transcript: "We had corn dogs.",
  transcript_state: "done",
  extraction_state: "done",
  audio_state: null,
};
const PLACED = {
  event_id: 30,
  event_title: "Fair week",
  period_id: 3,
  period_title: "Erie years",
  created_for_this_memory: false,
};
const PLACEMENT = {
  saved_to: PLACED,
  suggestions: [
    {
      kind: "event",
      label: "Erie years, Fair week",
      reason: "the closest event in time",
      event_id: 30,
      period_id: 3,
    },
    {
      kind: "period",
      label: "Erie years, a new event",
      reason: "the period these dates fall in",
      period_id: 3,
    },
    {
      kind: "new",
      label: "The 1960s, a new event",
      reason: "nothing covers these dates yet",
      decade: 1960,
    },
  ],
  recent: [{ id: 31, title: "Summer job", date_text: "summer 1968" }],
  nearby: [{ id: 30, title: "Fair week", date_text: "August 1968" }],
};

afterEach(() => vi.unstubAllGlobals());

test("a memory says where it was saved and can be moved", async () => {
  const { calls } = fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/memories/5": ok(MEMORY),
    "GET /api/memories/5/placement": ok(PLACEMENT),
    "POST /api/memories/5/place": ok({
      memory: { ...MEMORY, event_id: 31 },
      saved_to: { ...PLACED, event_id: 31, event_title: "Summer job" },
    }),
  });
  renderApp("/memories/5", PHONE);
  expect(await screen.findByText("Erie years, Fair week")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Change" }));
  const sheet = await screen.findByRole("region", {
    name: "Where does this memory go?",
  });
  expect(
    within(sheet).getByRole("button", { name: "Erie years, Fair week" }),
  ).toBeInTheDocument();
  fireEvent.click(
    within(sheet).getByRole("button", { name: "Summer job, summer 1968" }),
  );
  await waitFor(() =>
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      event_id: 31,
    }),
  );
  expect(await screen.findByText("Erie years, Summer job")).toBeInTheDocument();
});

test("somewhere new takes the decade from a tap", async () => {
  const { calls } = fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/memories/5": ok(MEMORY),
    "GET /api/memories/5/placement": ok({ ...PLACEMENT, saved_to: null }),
    "POST /api/dates/parse": ok({
      ok: true,
      reading: "the 1950s",
      start: "1950-01-01",
      end: "1959-12-31",
      precision: "decade",
      message: null,
      examples: [],
    }),
    "POST /api/memories/5/place": ok({
      memory: MEMORY,
      saved_to: {
        ...PLACED,
        period_title: "The 1950s",
        event_title: "Corn dogs at the fair",
        created_for_this_memory: false,
      },
    }),
  });
  renderApp("/memories/5", WIDE);
  expect(await screen.findByText("Waiting to be placed.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Place it" }));
  fireEvent.click(await screen.findByText("Somewhere new"));
  fireEvent.click(screen.getByRole("button", { name: "1950s" }));
  expect(screen.getByLabelText("When")).toHaveValue("the 1950s");
  fireEvent.click(screen.getByRole("button", { name: "Put it there" }));
  await waitFor(() =>
    expect(
      calls.find((c) => c.path === "/api/memories/5/place")?.body,
    ).toMatchObject({
      new_period: { title: "The 1950s", start_text: "1950", end_text: "1959" },
      date_text: "the 1950s",
    }),
  );
});

test("the inbox places a memory with one tap and empties", async () => {
  let placed = false;
  const { calls } = fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/inbox": () =>
      Response.json(
        placed
          ? { items: [], next_cursor: null }
          : {
              items: [{ memory: MEMORY, suggestion: PLACEMENT.suggestions[0] }],
              next_cursor: null,
            },
      ),
    "POST /api/inbox/5/accept": () => {
      placed = true;
      return Response.json({ memory: MEMORY, saved_to: PLACED });
    },
  });
  renderApp("/inbox", PHONE);
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Place in Erie years, Fair week",
    }),
  );
  expect(await screen.findByText("Nothing is waiting")).toBeInTheDocument();
  expect(
    await screen.findByText("Saved to Erie years, Fair week"),
  ).toBeInTheDocument();
  expect(calls.some((c) => c.path === "/api/inbox/5/accept")).toBe(true);
});

const TIMELINE = {
  person: { id: 1, name: "Corey", aliases: [] },
  periods: [
    {
      id: 3,
      person_id: 1,
      title: "Erie years",
      slug: "erie-years",
      start_text: "1967",
      end_text: "1970",
      event_count: 2,
      epic_count: 0,
      created_for_memory: false,
    },
    {
      id: 4,
      person_id: 1,
      title: "The 1980s",
      slug: "the-1980s",
      start_text: "1980",
      end_text: "1989",
      event_count: 1,
      epic_count: 0,
      created_for_memory: true,
    },
  ],
  next_cursor: null,
  unplaced_events: 0,
};

test("the timeline opens a chapter, and the open chapters are kept in the address", async () => {
  fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/me/person": ok({ id: 1, name: "Corey", aliases: [] }),
    "GET /api/people/1/timeline": ok(TIMELINE),
    "GET /api/people/1/events": (request: Request) => {
      const period = new URL(request.url).searchParams.get("period_id");
      return Response.json({
        items:
          period === "3"
            ? [
                {
                  id: 30,
                  title: "Fair week",
                  date_text: "August 1968",
                  participants: [],
                },
              ]
            : [
                {
                  id: 40,
                  title: "The lake house",
                  date_text: "summer 1985",
                  auto_created_for_memory_id: 9,
                  participants: [],
                },
              ],
        next_cursor: null,
      });
    },
  });
  const router = renderApp("/timeline?open=4", WIDE);
  expect(
    await screen.findByRole("heading", { name: "Corey's timeline" }),
  ).toBeInTheDocument();
  expect(
    await screen.findByRole("link", { name: "The lake house" }),
  ).toBeInTheDocument();
  // The period and its event are both labelled as made for a memory.
  expect(screen.getAllByText(/created for a memory/)).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: /Erie years/ }));
  expect(
    await screen.findByRole("link", { name: "Fair week" }),
  ).toHaveAttribute("href", "/events/30");
  await waitFor(() => expect(router.state.location.search).toBe("?open=3%2C4"));
});
