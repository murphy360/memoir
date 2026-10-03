import { Link } from "react-router";

import { Can } from "../auth/RequireAuth";
import { useMe } from "../auth/useMe";

/** A placeholder home until the shell ticket gives the app its two postures. */
export function HomePage() {
  const me = useMe();
  return (
    <main>
      <h1>Memoir</h1>
      <p>Signed in as {me.data?.display_name}.</p>
      <nav aria-label="Main">
        <ul>
          <li>
            <Link to="/profile">Your account</Link>
          </li>
          <Can role="owner">
            <li>
              <Link to="/settings/users">People with access</Link>
            </li>
          </Can>
          <li>
            <Link to="/status">System status</Link>
          </li>
        </ul>
      </nav>
    </main>
  );
}
