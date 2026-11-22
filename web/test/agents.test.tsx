import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { fakeApi, ok, OWNER } from "./fakeApi";
import { renderApp, WIDE } from "./renderApp";

afterEach(() => vi.unstubAllGlobals());

const CLAUDE = {
  id: 3,
  name: "Claude",
  connected_at: "2026-11-20T10:00:00Z",
  last_used_at: "2026-11-21T09:30:00Z",
};

test("the profile lists connected agents and disconnects one", async () => {
  let connected = [CLAUDE];
  const { calls } = fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/me/sessions": ok([]),
    "GET /api/me/agents": () => Response.json(connected),
    "DELETE /api/me/agents/3": () => {
      connected = [];
      return new Response(null, { status: 204 });
    },
  });
  renderApp("/profile", WIDE);
  expect(
    await screen.findByRole("heading", { name: "Connected agents" }),
  ).toBeInTheDocument();
  expect(await screen.findByText("Claude")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Disconnect Claude" }));
  const dialog = await screen.findByRole("dialog");
  expect(
    within(dialog).getByText(/can no longer read or tell stories as you/),
  ).toBeVisible();
  fireEvent.click(within(dialog).getByRole("button", { name: "Disconnect" }));
  await waitFor(() =>
    expect(calls.some((c) => c.method === "DELETE")).toBe(true),
  );
  expect(
    await screen.findByText("Claude is disconnected."),
  ).toBeInTheDocument();
  expect(await screen.findByText(/No assistant is connected/)).toBeVisible();
});

test("with no agent it says how to connect one", async () => {
  fakeApi({
    "GET /api/me": ok(OWNER),
    "GET /api/me/sessions": ok([]),
    "GET /api/me/agents": ok([]),
  });
  renderApp("/profile");
  expect(
    await screen.findByText(/add Memoir to it as a connector/),
  ).toBeInTheDocument();
});
