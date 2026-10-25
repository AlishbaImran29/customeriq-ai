// Support inbox (browser side): /api/v1/inbox.

import { apiGet, apiPatchJson, apiPostJson } from "@/lib/api/config";

export type Conversation = { customerId: number; customerName: string; phone: string | null; lastText: string | null; lastAt: string; lastFrom: "customer" | "us"; unread: number; status: "open" | "closed"; assignedTo: string | null; intent: string };
export type ThreadItem = { at: string; direction: "in" | "out"; text: string | null; kind: string; status: string | null; error: string | null };
export type Suggestion = { intent: string; escalate: boolean; reason: string | null; draft: string | null; sources: string[]; label: string };
export type Thread = {
  customerId: number; customerName: string; phone: string | null; status: "open" | "closed"; assignedTo: string | null; sessionOpen: boolean;
  items: ThreadItem[]; notes: { id: number; author: string | null; body: string; at: string }[]; suggestion: Suggestion | null;
};
export type Faq = { id: number; title: string; keywords: string; answer: string };

const P = "/api/v1/inbox";
export const listConversations = (state?: "open" | "closed") => apiGet<Conversation[]>(`${P}${state ? `?state=${state}` : ""}`);
export const getThread = (id: number) => apiGet<Thread>(`${P}/${id}`);
export const sendReply = (id: number, text: string) => apiPostJson<ThreadItem>(`${P}/${id}/reply`, { text });
export const addNote = (id: number, body: string) => apiPostJson<unknown>(`${P}/${id}/notes`, { body });
export const assignConversation = (id: number, patch: { assignedTo?: string; status?: "open" | "closed" }) => apiPatchJson<{ status: string; assignedTo: string | null }>(`${P}/${id}`, patch);
export const responseMetrics = () => apiGet<{ averageResponseMinutes: number | null; questionsMeasured: number; days: number; note: string }>(`${P}/metrics`);
export const listFaq = () => apiGet<Faq[]>(`${P}/faq/list`);
export const addFaq = (body: Omit<Faq, "id">) => apiPostJson<Faq>(`${P}/faq/list`, body);
