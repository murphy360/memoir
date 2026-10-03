import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";

import { makeQueryClient } from "./app/queryClient";
import { makeRouter } from "./app/router";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={makeQueryClient()}>
      <RouterProvider router={makeRouter(import.meta.env.BASE_URL)} />
    </QueryClientProvider>
  </StrictMode>,
);
