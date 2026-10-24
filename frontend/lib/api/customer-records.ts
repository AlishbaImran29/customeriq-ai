// Customer records (browser side): notes, tags, timeline, duplicates, merge, erase, audit. /api/v1/customer-records.

import { apiGet, apiPatchJson, apiPostJson } from "@/lib/api/config";

export type CustomerProfile = {
  id: number;
  customerId: string;
  name: string;
  email: string | null;
  phone: string | null;
  notes: string | null;
  tags: string[];
  acquisitionSource: string | null;
  status: "active" | "blocked" | "anonymised";
};
export type TimelineEvent = { at: string; kind: "order" | "status" | "message" | "reply" | "consent"; text: string };
export type DuplicateGroup = { reason: string; customers: CustomerProfile[] };
export type AuditRow = { id: number; action: string; customerRef: string; detail: Record<string, unknown>; at: string };

const P = "/api/v1/customer-records";
const q = (id: string) => `?id=${encodeURIComponent(id)}`;

export const getProfile = (id: string) => apiGet<CustomerProfile>(`${P}/profile${q(id)}`);
export const saveProfile = (id: string, patch: Partial<{ notes: string; tags: string[]; acquisitionSource: string; status: "active" | "blocked" }>) =>
  apiPatchJson<CustomerProfile>(`${P}/profile${q(id)}`, patch);
export const getTimeline = (id: string) => apiGet<TimelineEvent[]>(`${P}/timeline${q(id)}`);
export const listDuplicates = () => apiGet<DuplicateGroup[]>(`${P}/duplicates`);
export const mergeCustomers = (keepId: number, mergeId: number) => apiPostJson<CustomerProfile>(`${P}/merge`, { keepId, mergeId, confirm: true });
export const anonymiseCustomer = (customerId: string) => apiPostJson<CustomerProfile>(`${P}/anonymise`, { customerId, confirm: true });
export const deleteCustomer = (customerId: string) => apiPostJson<void>(`${P}/delete`, { customerId, confirm: true });
export const listAudit = () => apiGet<AuditRow[]>(`${P}/audit`);
