// Team roles and the action log (owner only): /api/v1/team and /api/v1/audit.

import { apiGet, apiPatchJson } from "@/lib/api/config";

export type Role = "owner" | "staff" | "viewer";
export type Member = { id: string; email: string; name: string; role: Role; isActive: boolean; lastLoginAt: string | null };
export type AuditRow = { id: number; at: string; actorEmail: string; actorRole: string; method: string; route: string; outcome: "allowed" | "denied"; detail: { ids?: Record<string, string> } };

export const ROLE_TEXT: Record<Role, string> = {
  owner: "Owner: can do everything",
  staff: "Staff: daily work, but no settings, deletions, exports or refund payments",
  viewer: "Viewer: can only look",
};

export const listMembers = () => apiGet<Member[]>("/api/v1/team/users");
export const changeMember = (id: string, patch: Partial<{ role: Role; isActive: boolean }>) => apiPatchJson<Member>(`/api/v1/team/users/${id}`, patch);
export const listActions = (outcome?: "allowed" | "denied") => apiGet<AuditRow[]>(`/api/v1/audit${outcome ? `?outcome=${outcome}` : ""}`);
