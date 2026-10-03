import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";

import { routes } from "../src/app/router";
import { ToastProvider } from "../src/components/Toast";
import { setWidth } from "./setup";

/** The whole app at `path`, in the phone posture unless a width is given. */
export function renderApp(path: string, width = 390) {
  setWidth(width);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return router;
}

export const PHONE = 390;
export const WIDE = 1280;
