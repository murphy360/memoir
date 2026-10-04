import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type ErrorBody = components["schemas"]["ErrorBody"];

/** An error the API returned, in its structured shape ({code, message, field}). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field: string | null;

  constructor(status: number, body: Partial<ErrorBody> | undefined) {
    super(body?.message ?? `The server answered ${status}.`);
    this.status = status;
    this.code = body?.code ?? "http_error";
    this.field = body?.field ?? null;
  }
}

/** The API's base URL: the same origin, under the app's base path (`/memoir/` in production). */
export function apiBaseUrl(origin: string, basePath: string): string {
  return `${origin}${basePath.replace(/\/$/, "")}`;
}

/** The typed client: every path, parameter and response comes from the API's OpenAPI document. */
export const api = createClient<paths>({
  baseUrl: apiBaseUrl(window.location.origin, import.meta.env.BASE_URL),
  // Looked up on each call rather than captured once, so tests can stand in for the network.
  fetch: (request) => globalThis.fetch(request),
});

/** Unwraps an openapi-fetch result: the data, or an ApiError carrying the structured body. */
export function unwrap<T>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): T {
  if (result.error !== undefined || result.data === undefined) {
    const body = (result.error as { error?: ErrorBody } | undefined)?.error;
    throw new ApiError(result.response.status, body);
  }
  return result.data;
}
