import { fireEvent, screen, waitFor } from "@testing-library/react";

import { safeNext } from "../src/auth/LoginPage";
import { fail, fakeApi, ok, OWNER, VIEWER } from "./fakeApi";
import { renderApp } from "./renderApp";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "memoir_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

test("someone not signed in is sent to sign in, then back where they were going", async () => {
  let signedIn = false;
  const { calls } = fakeApi({
    "GET /api/me": () =>
      signedIn
        ? Response.json(OWNER)
        : Response.json(
            { error: { code: "unauthenticated", message: "Please sign in." } },
            {
              status: 401,
            },
          ),
    "POST /api/auth/login": () => {
      signedIn = true;
      return Response.json(OWNER);
    },
  });
  const router = renderApp("/profile");
  expect(
    await screen.findByRole("heading", { name: "Sign in to Memoir" }),
  ).toBeInTheDocument();
  expect(router.state.location.search).toBe("?next=%2Fprofile");

  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "owner@example.org" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "a long phrase" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

  expect(
    await screen.findByRole("heading", { name: "Your account" }),
  ).toBeInTheDocument();
  const login = calls.find((c) => c.path === "/api/auth/login");
  expect(login?.body).toEqual({
    email: "owner@example.org",
    password: "a long phrase",
  });
});

test("a refused sign-in shows the server's message", async () => {
  fakeApi({
    "GET /api/me": fail(401, "unauthenticated", "Please sign in."),
    "POST /api/auth/login": fail(
      401,
      "login_failed",
      "That email and password do not match an account.",
    ),
  });
  renderApp("/login");
  fireEvent.change(await screen.findByLabelText("Email"), {
    target: { value: "a@b.c" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "wrong wrong" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "That email and password do not match an account.",
  );
});

test("a temporary password sends the user to choose a new one first", async () => {
  fakeApi({ "GET /api/me": ok({ ...OWNER, must_change_password: true }) });
  const router = renderApp("/");
  expect(
    await screen.findByRole("heading", { name: "Choose a new password" }),
  ).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/change-password");
});

test("a viewer sees no owner controls, and the owner page refuses them plainly", async () => {
  fakeApi({ "GET /api/me": ok(VIEWER) });
  renderApp("/");
  expect(await screen.findByText("Signed in as Ann.")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "People with access" })).toBeNull();
});

test("the owner sees the owner link", async () => {
  fakeApi({ "GET /api/me": ok(OWNER) });
  renderApp("/");
  expect(
    await screen.findByRole("link", { name: "People with access" }),
  ).toBeInTheDocument();
});

test("the owner page refuses a viewer who types its address", async () => {
  fakeApi({ "GET /api/me": ok(VIEWER) });
  renderApp("/settings/users");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "This page is for the archive's owners.",
  );
});

test("every change carries the session's CSRF token", async () => {
  document.cookie = "memoir_csrf=tok123";
  const { calls } = fakeApi({
    "GET /api/me": ok(OWNER),
    "PATCH /api/me": ok({ ...OWNER, display_name: "Corey M" }),
  });
  renderApp("/profile");
  fireEvent.change(await screen.findByLabelText("Your name"), {
    target: { value: "Corey M" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save name" }));
  await waitFor(() =>
    expect(calls.some((c) => c.method === "PATCH")).toBe(true),
  );
  const patch = calls.find((c) => c.method === "PATCH");
  expect(patch?.headers.get("X-CSRF-Token")).toBe("tok123");
  expect(
    calls.find((c) => c.method === "GET")?.headers.get("X-CSRF-Token"),
  ).toBeNull();
});

test("an invitation that is gone says so", async () => {
  fakeApi({
    "GET /api/me": fail(401, "unauthenticated", "Please sign in."),
    "GET /api/invitations/accept/abc": fail(
      410,
      "invitation_gone",
      "This invitation has expired or was already used. Ask for a new one.",
    ),
  });
  renderApp("/invite/abc");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Ask for a new one.",
  );
});

test("accepting an invitation signs the new member in", async () => {
  const { calls } = fakeApi({
    "GET /api/me": fail(401, "unauthenticated", "Please sign in."),
    "GET /api/invitations/accept/abc": ok({
      email: "mary@example.org",
      role: "contributor",
      archive_name: "The Murphys",
      invited_by: "Corey",
    }),
    "POST /api/invitations/accept/abc": ok({
      ...OWNER,
      id: 3,
      display_name: "Mary",
      role: "contributor",
    }),
  });
  const router = renderApp("/invite/abc");
  expect(
    await screen.findByRole("heading", { name: "Join The Murphys" }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Your name, as the family knows it"), {
    target: { value: "Mary" },
  });
  fireEvent.change(screen.getByLabelText("Choose a password"), {
    target: { value: "marys own phrase" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Join" }));
  await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({
    display_name: "Mary",
    password: "marys own phrase",
  });
});

test("after signing in, only paths inside the app are followed", () => {
  expect(safeNext("/profile")).toBe("/profile");
  expect(safeNext("//evil.example")).toBe("/");
  expect(safeNext("https://evil.example")).toBe("/");
  expect(safeNext(null)).toBe("/");
});
