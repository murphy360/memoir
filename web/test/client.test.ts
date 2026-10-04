import { ApiError, apiBaseUrl, unwrap } from "../src/api/client";

test("the API is on the same origin under the base path", () => {
  expect(apiBaseUrl("https://dontpanic.ddns.net", "/memoir/")).toBe(
    "https://dontpanic.ddns.net/memoir",
  );
  expect(apiBaseUrl("http://localhost:5173", "/")).toBe(
    "http://localhost:5173",
  );
});

test("unwrap returns the data of a success", () => {
  const response = new Response(null, { status: 200 });
  expect(unwrap({ data: { ok: true }, response })).toEqual({ ok: true });
});

test("unwrap throws the structured error of a failure", () => {
  const response = new Response(null, { status: 503 });
  const error = {
    error: {
      code: "database_unavailable",
      message: "The database is not reachable.",
    },
  };
  expect(() => unwrap({ error, response })).toThrow(ApiError);
  try {
    unwrap({ error, response });
  } catch (e) {
    expect(e).toMatchObject({ status: 503, code: "database_unavailable" });
  }
});
