import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";

import { DateField } from "../src/components/DateField";
import { fakeApi, ok } from "./fakeApi";

function Harness() {
  const [value, setValue] = useState("");
  const [keep, setKeep] = useState(false);
  return (
    <>
      <DateField
        label="When"
        value={value}
        onChange={setValue}
        keepTextOnly={keep}
        onKeepTextOnlyChange={setKeep}
      />
      <output>{keep ? "keeping text" : "reading only"}</output>
    </>
  );
}

function renderField() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

test("shows how a date reads before it is saved", async () => {
  const { calls } = fakeApi({
    "POST /api/dates/parse": ok({
      ok: true,
      start: "1968-06-01",
      end: "1968-08-31",
      precision: "approximate",
      reading: "Summer 1968",
      message: null,
      examples: [],
    }),
  });
  renderField();
  expect(screen.getByText(/Any way you would say it/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("When"), {
    target: { value: "summer 1968" },
  });
  expect(await screen.findByText("Reads as Summer 1968")).toBeInTheDocument();
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({
    text: "summer 1968",
  });
});

test("warns when it cannot read a date and offers to keep the text", async () => {
  fakeApi({
    "POST /api/dates/parse": ok({
      ok: false,
      start: null,
      end: null,
      precision: null,
      reading: null,
      message: "Could not read this date.",
      examples: ["July 16, 1968", "summer 1968", "the 1960s"],
    }),
  });
  renderField();
  fireEvent.change(screen.getByLabelText("When"), {
    target: { value: "senior year" },
  });
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Memoir cannot read this date",
  );
  expect(
    screen.getByText(/Try: July 16, 1968; summer 1968; the 1960s/),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Save it as written anyway"));
  expect(screen.getByText("keeping text")).toBeInTheDocument();
});
