import type { components } from "./schema";

type Schemas = components["schemas"];

export type Me = Schemas["Me"];
export type Role = Schemas["Role"];
export type UserOut = Schemas["UserOut"];
export type InvitationOut = Schemas["InvitationOut"];
export type CreatedInvitation = Schemas["CreatedInvitation"];
export type InvitationPreview = Schemas["InvitationPreview"];
export type SessionInfo = Schemas["SessionInfo"];

const RANK: Record<Role, number> = { viewer: 0, contributor: 1, owner: 2 };

/** Whether a user's role includes `role` (owner includes contributor includes viewer). */
export function atLeast(user: Pick<Me, "role">, role: Role): boolean {
  return RANK[user.role] >= RANK[role];
}
