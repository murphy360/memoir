import { useQuery } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "../api/client";
import type { Me } from "../api/types";

export const ME = ["me"] as const;

/** The signed-in user, or null when nobody is signed in. Other failures are errors. */
export function useMe() {
  return useQuery<Me | null>({
    queryKey: ME,
    queryFn: async () => {
      try {
        return unwrap(await api.GET("/api/me"));
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: 60_000,
  });
}
