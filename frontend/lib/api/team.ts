// Team roles (owner only): /api/v1/team.

import { apiGet, apiPatchJson } from "@/lib/api/config";

export type Role = "owner" | "staff" | "viewer";
export type Member = { id: string; email: string; name: string; role: Role; isActive: boolean; lastLoginAt: string | null };

export const ROLE_TEXT: Record<Role, string> = {
  owner: "Owner: can do everything",
  staff: "Staff: daily work, but no settings, deletions, exports or refund payments",
  viewer: "Viewer: can only look",
};

export const listMembers = () => apiGet<Member[]>("/api/v1/team/users");
export const changeMember = (id: string, patch: Partial<{ role: Role; isActive: boolean }>) => apiPatchJson<Member>(`/api/v1/team/users/${id}`, patch);
