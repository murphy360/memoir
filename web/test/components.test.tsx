import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { ApiError } from "../src/api/client";
import { ErrorText } from "../src/components/Form";
import { ToastProvider } from "../src/components/Toast";
import { messageOf } from "../src/lib/errors";
import { useStoredState } from "../src/lib/storedState";
import { GalleryPage } from "../src/pages/GalleryPage";
import { fakeApi, ok } from "./fakeApi";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

test("stored state survives a remount", () => {
  const first = renderHook(() => useStoredState("panel", false));
  act(() => first.result.current[1](true));
  first.unmount();
  const again = renderHook(() => useStoredState("panel", false));
  expect(again.result.current[0]).toBe(true);
  expect(localStorage.getItem("memoir:panel")).toBe("true");
});

test("errors read as the server's sentence, or plainly", () => {
  expect(
    messageOf(
      new ApiError(409, { code: "x", message: "Someone has that name." }),
    ),
  ).toBe("Someone has that name.");
  expect(messageOf(new TypeError("Failed to fetch"))).toBe(
    "Memoir could not reach the server. Check the connection.",
  );
  render(<ErrorText error={new ApiError(500, undefined)} />);
  expect(screen.getByRole("alert")).toHaveTextContent(
    "The server answered 500.",
  );
});

function gallery() {
  fakeApi({
    "POST /api/dates/parse": ok({
      ok: true,
      reading: "Summer 1968",
      start: "1968-06-01",
      end: "1968-08-31",
      precision: "approximate",
      message: null,
      examples: [],
    }),
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ToastProvider>
        <MemoryRouter>
          <GalleryPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

test("a confirmation says what will happen and answers yes or no", async () => {
  gallery();
  fireEvent.click(screen.getByRole("button", { name: "Ask to confirm" }));
  expect(
    await screen.findByText(/Its 3 epics move to Childhood/),
  ).toBeInTheDocument();
  fireEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }),
  );
  expect(await screen.findByText("Confirmed")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Ask to confirm" }));
  fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
  expect(await screen.findByText("Cancelled")).toBeInTheDocument();
});

test("toasts announce success politely and errors as alerts, and can be dismissed", async () => {
  gallery();
  fireEvent.click(screen.getByRole("button", { name: "Show a success" }));
  expect(await screen.findByText("Saved.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show an error" }));
  const alert = await screen.findByText("The server said no.");
  expect(alert.closest("[role=alert]")).not.toBeNull();
  fireEvent.click(screen.getAllByRole("button", { name: "Dismiss" })[0]!);
  expect(screen.queryByText("Saved.")).toBeNull();
});
