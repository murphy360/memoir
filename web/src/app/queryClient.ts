import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";

/** One cache for the whole app. A 4xx is the caller's to fix, so only other failures retry. */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (count, error) =>
          !(error instanceof ApiError && error.status < 500) && count < 2,
        staleTime: 10_000,
      },
    },
  });
}
