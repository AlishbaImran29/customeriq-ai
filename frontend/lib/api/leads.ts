// Leads (browser side): /api/v1/leads.

import { apiGet, apiPatchJson, apiPostJson } from "@/lib/api/config";

export type Stage = "new" | "contacted" | "interested" | "converted" | "lost";
export const STAGES: Stage[] = ["new", "contacted", "interested", "converted", "lost"];
export type Lead = {
  id: number;
  name: string | null;
  phone: string | null;
  email: string | null;
  source: string;
  campaign: string | null;
  utmSource: string | null;
  utmMedium: string | null;
  utmCampaign: string | null;
  productInterest: string | null;
  stage: Stage;
  notes: string | null;
  lostReason: string | null;
  customerId: number | null;
  followUpAt: string | null;
  contactedAt: string | null;
  createdAt: string;
  overdue: boolean;
  allowedNext: Stage[];
};
export type LeadSummary = { stages: Record<Stage, number>; overdue: number; slaHours: number };
export type LeadEvent = { event: string; detail: Record<string, unknown>; at: string };
export type NewLead = { name?: string; phone?: string; email?: string; campaign?: string; utmSource?: string; productInterest?: string; notes?: string };

const P = "/api/v1/leads";
export const listLeads = (stage?: Stage) => apiGet<Lead[]>(`${P}${stage ? `?stage=${stage}` : ""}`);
export const leadSummary = () => apiGet<LeadSummary>(`${P}/summary`);
export const addLead = (body: NewLead) => apiPostJson<Lead>(P, body);
export const moveLead = (id: number, stage: Stage, extra: { lostReason?: string; followUpInHours?: number } = {}) => apiPostJson<Lead>(`${P}/${id}/move`, { stage, ...extra });
export const saveLeadNotes = (id: number, notes: string) => apiPatchJson<Lead>(`${P}/${id}`, { notes });
export const leadEvents = (id: number) => apiGet<LeadEvent[]>(`${P}/${id}/events`);
