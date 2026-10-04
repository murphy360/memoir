import { createBrowserRouter } from "react-router";

import { ChangePasswordPage } from "../auth/ChangePasswordPage";
import { InvitePage } from "../auth/InvitePage";
import { LoginPage } from "../auth/LoginPage";
import { ProfilePage } from "../auth/ProfilePage";
import { RequireAuth, RequireRole } from "../auth/RequireAuth";
import { GalleryPage } from "../pages/GalleryPage";
import { HealthPage } from "../pages/HealthPage";
import { EventPage, PeoplePage, PersonPage } from "../pages/PeoplePages";
import { InboxPage } from "../features/inbox/InboxPage";
import { MemoryPage } from "../features/memories/MemoryPage";
import { RecordScreen } from "../features/record/RecordScreen";
import {
  MyTimelinePage,
  PersonTimelinePage,
} from "../features/timeline/TimelinePage";
import { HomePage, NotFoundPage, QuestionsPage } from "../pages/Placeholders";
import { UsersPage } from "../settings/UsersPage";
import { AppShell } from "./Layouts";

/** Every signed-in page, each reachable in both postures. */
export const shellRoutes = [
  // The phone greets; the wide screen opens the review workspace.
  { path: "/", element: <HomePage />, title: "Hello|Your family's memoir" },
  { path: "/record", element: <RecordScreen />, title: "Record a memory" },
  { path: "/timeline", element: <MyTimelinePage />, title: "timeline" },
  { path: "/people", element: <PeoplePage />, title: "People" },
  { path: "/people/:id", element: <PersonPage /> },
  { path: "/people/:id/timeline", element: <PersonTimelinePage /> },
  { path: "/events/:id", element: <EventPage /> },
  { path: "/memories/:id", element: <MemoryPage /> },
  {
    path: "/questions",
    element: <QuestionsPage />,
    title: "Questions for you",
  },
  { path: "/inbox", element: <InboxPage />, title: "Waiting to be placed" },
  { path: "/profile", element: <ProfilePage />, title: "Your account" },
  { path: "/status", element: <HealthPage />, title: "Memoir" },
  { path: "/gallery", element: <GalleryPage />, title: "Design pieces" },
  {
    path: "/settings/users",
    element: (
      <RequireRole role="owner">
        <UsersPage />
      </RequireRole>
    ),
    title: "People with access",
  },
  { path: "*", element: <NotFoundPage />, title: "Not here" },
];

export const routes = [
  { path: "/login", element: <LoginPage /> },
  { path: "/invite/:token", element: <InvitePage /> },
  {
    element: <RequireAuth />,
    children: [
      { path: "/change-password", element: <ChangePasswordPage /> },
      {
        element: <AppShell />,
        children: shellRoutes.map(({ path, element }) => ({ path, element })),
      },
    ],
  },
];

export function makeRouter(basename: string) {
  return createBrowserRouter(routes, { basename });
}
