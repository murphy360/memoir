import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import { HealthPage } from "../src/pages/HealthPage";

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <HealthPage />
    </QueryClientProvider>,
  );
}

function answer(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json(body, { status })),
  );
}

afterEach(() => vi.unstubAllGlobals());

test("shows the database and the worker", async () => {
  answer(200, {
    status: "ok",
    version: "0.1.0",
    database: "ok",
    worker: { status: "ok", last_seen: "2026-10-03T12:00:00Z", age_seconds: 3 },
  });
  renderPage();
  expect(await screen.findByText("Database")).toBeInTheDocument();
  expect(screen.getAllByText("ok")).toHaveLength(3);
  expect(screen.getByText("0.1.0")).toBeInTheDocument();
});

test("shows the server's message when the database is down", async () => {
  answer(503, {
    error: {
      code: "database_unavailable",
      message: "The database is not reachable.",
      field: null,
    },
  });
  renderPage();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The database is not reachable.",
  );
});
