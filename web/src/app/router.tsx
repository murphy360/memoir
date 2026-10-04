import { createBrowserRouter } from "react-router";

import { ChangePasswordPage } from "../auth/ChangePasswordPage";
import { InvitePage } from "../auth/InvitePage";
import { LoginPage } from "../auth/LoginPage";
import { ProfilePage } from "../auth/ProfilePage";
import { RequireAuth, RequireRole } from "../auth/RequireAuth";
import { HealthPage } from "../pages/HealthPage";
import { HomePage } from "../pages/HomePage";
import { UsersPage } from "../settings/UsersPage";

export const routes = [
  { path: "/login", element: <LoginPage /> },
  { path: "/invite/:token", element: <InvitePage /> },
  {
    element: <RequireAuth />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/change-password", element: <ChangePasswordPage /> },
      { path: "/profile", element: <ProfilePage /> },
      { path: "/status", element: <HealthPage /> },
      {
        path: "/settings/users",
        element: (
          <RequireRole role="owner">
            <UsersPage />
          </RequireRole>
        ),
      },
    ],
  },
];

/** The routes. The shell ticket adds the two postures and every screen. */
export function makeRouter(basename: string) {
  return createBrowserRouter(routes, { basename });
}
