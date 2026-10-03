import { createBrowserRouter } from "react-router";

import { HealthPage } from "../pages/HealthPage";

/** The routes. The shell ticket adds the two postures and every screen. */
export function makeRouter(basename: string) {
  return createBrowserRouter([{ path: "/", element: <HealthPage /> }], {
    basename,
  });
}
