import { Link, NavLink, Outlet } from "react-router";

import { Can } from "../auth/RequireAuth";
import { useMe } from "../auth/useMe";
import { NAV, type NavItem } from "./nav";
import { usePosture } from "./usePosture";

function Item({ item, tab }: { item: NavItem; tab?: boolean }) {
  const link = (
    <li>
      <NavLink
        to={item.to}
        end={item.to === "/"}
        className={tab ? "tab" : undefined}
      >
        {tab && item.short ? item.short : item.label}
      </NavLink>
    </li>
  );
  return item.role ? <Can role={item.role}>{link}</Can> : link;
}

function SkipLink() {
  return (
    <a className="skip" href="#main">
      Skip to content
    </a>
  );
}

/** The phone: capture first. Content above, five tabs below, everything else from them. */
function PhoneLayout() {
  return (
    <div className="phone">
      <SkipLink />
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
      <nav className="tabs" aria-label="Main">
        <ul>
          {NAV.filter((i) => i.tab).map((item) => (
            <Item key={item.to} item={item} tab />
          ))}
        </ul>
      </nav>
    </div>
  );
}

/** The wide screen: review first. Header with Record, navigation on the left, workspace. */
function WideLayout() {
  const me = useMe();
  return (
    <div className="wide">
      <SkipLink />
      <header className="topbar">
        <Link to="/" className="brand">
          Memoir
        </Link>
        <Link to="/record" className="button primary record">
          Record
        </Link>
        <Link to="/profile" className="who">
          {me.data?.display_name}
        </Link>
      </header>
      <nav className="sidebar" aria-label="Main">
        <ul>
          {NAV.map((item) => (
            <Item key={item.to} item={item} />
          ))}
        </ul>
      </nav>
      <main id="main" tabIndex={-1} className="workspace">
        <Outlet />
      </main>
    </div>
  );
}

/** Every signed-in page hangs in one of the two postures, chosen by the screen's width. */
export function AppShell() {
  return usePosture() === "wide" ? <WideLayout /> : <PhoneLayout />;
}
