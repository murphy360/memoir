import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router";

import type { Role } from "../api/types";
import { atLeast } from "../api/types";
import { ErrorText } from "../components/Form";
import { useMe } from "./useMe";

/**
 * Every signed-in page sits under this. Nobody signed in: off to the login page, with a
 * way back. A password change pending: off to that page first.
 */
export function RequireAuth() {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <p role="status">Loading…</p>;
  if (me.isError) return <ErrorText error={me.error} />;
  if (!me.data) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (
    me.data.must_change_password &&
    location.pathname !== "/change-password"
  ) {
    return <Navigate to="/change-password" replace />;
  }
  return <Outlet />;
}

/** Renders its children only for users whose role includes `role`. */
export function Can({ role, children }: { role: Role; children: ReactNode }) {
  const me = useMe();
  return me.data && atLeast(me.data, role) ? <>{children}</> : null;
}

/** A page only `role` and above may open; others get a plain refusal, not a blank page. */
export function RequireRole({
  role,
  children,
}: {
  role: Role;
  children: ReactNode;
}) {
  const me = useMe();
  if (!me.data) return null;
  if (!atLeast(me.data, role)) {
    return (
      <main>
        <p role="alert">This page is for the archive&apos;s {role}s.</p>
      </main>
    );
  }
  return <>{children}</>;
}
