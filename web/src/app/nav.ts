import type { Role } from "../api/types";

export type NavItem = {
  to: string;
  label: string;
  /** Shown in the phone's tab bar (at most five), with this shorter label if given. */
  tab?: boolean;
  short?: string;
  role?: Role;
};

/** The places in the app. Both postures show all of them; the phone tabs show five. */
export const NAV: NavItem[] = [
  { to: "/", label: "Home", tab: true },
  { to: "/timeline", label: "Timeline", tab: true },
  { to: "/people", label: "People", tab: true },
  { to: "/questions", label: "Questions", tab: true },
  { to: "/inbox", label: "Waiting to be placed" },
  { to: "/settings/users", label: "People with access", role: "owner" },
  { to: "/status", label: "System status" },
  { to: "/profile", label: "Your account", tab: true, short: "Account" },
];
