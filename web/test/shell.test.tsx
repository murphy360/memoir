import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { shellRoutes } from "../src/app/router";
import { fail, fakeApi, ok, OWNER } from "./fakeApi";
import { PHONE, renderApp, WIDE } from "./renderApp";

const PAGE = { items: [], next_cursor: null };

function api(extra = {}) {
  return fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/people": ok(PAGE),
    "GET /api/health": ok({
      status: "ok",
      version: "0.1.0",
      database: "ok",
      worker: { status: "ok", last_seen: null, age_seconds: 1 },
    }),
    "GET /api/me/sessions": ok([]),
    "GET /api/users": ok([]),
    "GET /api/invitations": ok([]),
    "GET /api/me/person": ok({ id: 1, name: "Corey", aliases: [] }),
    "GET /api/people/1/timeline": ok({
      person: { id: 1, name: "Corey", aliases: [] },
      periods: [],
      next_cursor: null,
      unplaced_events: 0,
    }),
    "GET /api/inbox": ok({ items: [], next_cursor: null }),
    "GET /api/questions/next": ok({ question: null, waiting: false }),
    "GET /api/questions/for-you": ok({ items: [] }),
    ...extra,
  });
}

afterEach(() => vi.unstubAllGlobals());

test("the phone posture has five tabs and no sidebar", async () => {
  api();
  renderApp("/", PHONE);
  const nav = await screen.findByRole("navigation", { name: "Main" });
  const tabs = within(nav)
    .getAllByRole("link")
    .map((a) => a.textContent);
  expect(tabs).toEqual(["Home", "Timeline", "People", "Questions", "Account"]);
  expect(
    screen.getByRole("link", { name: "Record a memory" }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("banner")).toBeNull();
});

test("the wide posture has a header with Record and the whole navigation", async () => {
  api();
  renderApp("/", WIDE);
  const header = await screen.findByRole("banner");
  expect(
    within(header).getByRole("link", { name: "Record" }),
  ).toBeInTheDocument();
  const nav = screen.getByRole("navigation", { name: "Main" });
  expect(
    within(nav)
      .getAllByRole("link")
      .map((a) => a.textContent),
  ).toEqual([
    "Home",
    "Timeline",
    "People",
    "Questions",
    "Waiting to be placed",
    "People with access",
    "System status",
    "Your account",
  ]);
  expect(
    screen.getByRole("heading", { name: "Your family's memoir" }),
  ).toBeInTheDocument();
});

const titled = shellRoutes.filter(
  (r) => r.title && !r.path.includes(":") && r.path !== "*",
);

describe.each([
  ["phone", PHONE],
  ["wide", WIDE],
])("every page is reachable in the %s posture", (_, width) => {
  test.each(titled.map((r) => [r.path, r.title]))("%s", async (path, title) => {
    api();
    renderApp(path as string, width);
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: new RegExp(title as string),
      }),
    ).toBeInTheDocument();
  });
});

test("a deep link to a person or an event lands on it after a reload", async () => {
  api({
    "GET /api/people/7": ok({ id: 7, name: "Grandma", aliases: [] }),
    "GET /api/events/9": ok({
      id: 9,
      title: "The wedding",
      date_text: "June 2008",
      participants: [{ person_id: 7, name: "Grandma" }],
    }),
  });
  renderApp("/people/7", WIDE);
  expect(
    await screen.findByRole("heading", { name: "Grandma" }),
  ).toBeInTheDocument();
});

test("an event deep link shows the event and its people", async () => {
  api({
    "GET /api/events/9": ok({
      id: 9,
      title: "The wedding",
      date_text: "June 2008",
      participants: [{ person_id: 7, name: "Grandma" }],
    }),
  });
  renderApp("/events/9", PHONE);
  expect(
    await screen.findByRole("heading", { name: "The wedding" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Grandma" })).toHaveAttribute(
    "href",
    "/people/7",
  );
});

test("an unknown address says so in both postures", async () => {
  api();
  renderApp("/nowhere", WIDE);
  expect(
    await screen.findByRole("heading", { name: "Not here" }),
  ).toBeInTheDocument();
});

test("a person who is not there shows the server's message", async () => {
  api({ "GET /api/people/404": fail(404, "not_found", "No such person.") });
  renderApp("/people/404");
  expect(await screen.findByRole("alert")).toHaveTextContent("No such person.");
});

test("the people search lives in the URL, so a reload keeps it", async () => {
  const { calls } = api({
    "GET /api/people": ok({
      items: [{ id: 1, name: "Ann", aliases: ["Annie"] }],
      next_cursor: null,
    }),
  });
  const router = renderApp("/people?q=ann", WIDE);
  const box = await screen.findByRole("searchbox");
  expect(box).toHaveValue("ann");
  await screen.findByRole("link", { name: "Ann" });
  const first = calls.find((c) => c.path === "/api/people");
  expect(first).toBeDefined();
  fireEvent.change(box, { target: { value: "annie" } });
  await waitFor(() => expect(router.state.location.search).toBe("?q=annie"));
});

test("a refused change is undone and the server's message is shown", async () => {
  fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/me/sessions": ok([]),
    "PATCH /api/me": fail(422, "invalid", "That name is too long."),
  });
  renderApp("/profile", WIDE);
  const name = await screen.findByLabelText("Your name");
  fireEvent.change(name, { target: { value: "Corey Murphy the Third" } });
  fireEvent.click(screen.getByRole("button", { name: "Save name" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "That name is too long.",
  );
  await waitFor(() =>
    expect(
      within(screen.getByRole("main")).getByText("Corey", {
        selector: "strong",
      }),
    ).toBeInTheDocument(),
  );
});
