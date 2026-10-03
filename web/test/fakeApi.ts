/** A stand-in for the API: routes `fetch` calls to handlers and records every request. */

/** A JSON body as an object; anything else (an audio chunk) as it came. */
function parsed(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

type Handler = (request: Request) => Response | Promise<Response>;

export type Recorded = {
  method: string;
  path: string;
  headers: Headers;
  body: unknown;
};

export function fakeApi(routes: Record<string, Handler>) {
  const calls: Recorded[] = [];
  const fetch = vi.fn(async (given: Request | string, init?: RequestInit) => {
    // The client passes a Request; the chunk upload passes a URL and options.
    const input = typeof given === "string" ? new Request(given, init) : given;
    const url = new URL(input.url);
    const path = url.pathname.replace(/^\/memoir/, "");
    const text = input.method === "GET" ? "" : await input.clone().text();
    calls.push({
      method: input.method,
      path,
      headers: input.headers,
      body: text ? parsed(text) : undefined,
    });
    const handler = routes[`${input.method} ${path}`];
    if (!handler)
      return Response.json(
        { error: { code: "not_found", message: path } },
        { status: 404 },
      );
    return handler(input);
  });
  vi.stubGlobal("fetch", fetch);
  return { calls };
}

export const ok =
  (body: unknown, status = 200) =>
  () =>
    Response.json(body, { status });
export const fail = (status: number, code: string, message: string) => () =>
  Response.json({ error: { code, message, field: null } }, { status });

export const OWNER = {
  id: 1,
  email: "owner@example.org",
  display_name: "Corey",
  role: "owner",
  is_executor: false,
  must_change_password: false,
};
export const VIEWER = { ...OWNER, id: 2, display_name: "Ann", role: "viewer" };
