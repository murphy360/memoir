import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";

import { makeQueryClient } from "./app/queryClient";
import { makeRouter } from "./app/router";
import { ToastProvider } from "./components/Toast";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={makeQueryClient()}>
      <ToastProvider>
        <RouterProvider router={makeRouter(import.meta.env.BASE_URL)} />
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);

// Installable as an app. The worker passes every request through: no offline promises yet.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  navigator.serviceWorker
    .register(`${import.meta.env.BASE_URL}sw.js`)
    .catch(() => undefined);
}
