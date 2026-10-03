import createClient, { type Middleware } from "openapi-fetch";

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

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** The session's CSRF token, which the API sets in a cookie the app can read. */
export function csrfToken(cookies: string = document.cookie): string | null {
  const match = cookies.match(/(?:^|;\s*)memoir_csrf=([^;]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

/** Every change carries the CSRF token in a header, as the API requires. */
export const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    const token = csrfToken();
    if (UNSAFE.has(request.method) && token) {
      request.headers.set("X-CSRF-Token", token);
    }
    return request;
  },
};

api.use(csrfMiddleware);

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
