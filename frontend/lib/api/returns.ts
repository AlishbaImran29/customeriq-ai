// Returns, refunds and tickets (browser side). The app never moves money: a refund is only ever "recorded" by the seller.

import { apiGet, apiPatchJson, apiPostForm, apiPostJson } from "@/lib/api/config";

export type ReturnStatus = "requested" | "approved" | "rejected" | "received" | "closed";
export type Refund = { id: number; returnId: number | null; orderId: number; orderNumber: string; amount: number; status: "requested" | "recorded"; method: string | null; reference: string | null; recordedAt: string | null };
export type Evidence = { id: number; kind: string; mimeType: string; sizeBytes: number; at: string; url: string | null };
export type ReturnEvent = { event: string; detail: Record<string, unknown>; by: string | null; at: string };
export type ReturnRow = {
  id: number; orderId: number; orderNumber: string; customerName: string; orderTotal: number; reason: string; status: ReturnStatus;
  resolution: string | null; decisionNote: string | null; restocked: boolean; replacementOrderId: number | null; createdAt: string;
  evidence: Evidence[]; events: ReturnEvent[]; refunds: Refund[];
};
export type Ticket = {
  id: number; customerId: number | null; customerName: string | null; orderId: number | null; subject: string; body: string | null;
  status: "open" | "in_progress" | "resolved" | "closed"; priority: "low" | "normal" | "high"; assignedTo: string | null; createdAt: string; resolvedAt: string | null;
  notes: { id: number; author: string | null; text: string; at: string }[];
};

const R = "/api/v1/returns";
export const listReturns = (status?: ReturnStatus) => apiGet<ReturnRow[]>(`${R}${status ? `?status=${status}` : ""}`);
export const getReturn = (id: number) => apiGet<ReturnRow>(`${R}/${id}`);
export const createReturn = (orderId: number, reason: string) => apiPostJson<ReturnRow>(R, { orderId, reason });
export const approveReturn = (id: number, resolution: "refund" | "replacement" | "none", amount?: number, note?: string) => apiPostJson<ReturnRow>(`${R}/${id}/approve`, { resolution, amount, note });
export const rejectReturn = (id: number, note?: string) => apiPostJson<ReturnRow>(`${R}/${id}/reject`, { note });
export const receiveReturn = (id: number, restock: boolean) => apiPostJson<ReturnRow>(`${R}/${id}/receive`, { restock });
export const closeReturn = (id: number) => apiPostJson<ReturnRow>(`${R}/${id}/close`, {});
export const addEvidence = (id: number, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<Evidence>(`${R}/${id}/evidence`, form);
};
export const recordRefund = (id: number, method: string, reference?: string) => apiPostJson<Refund>(`/api/v1/refunds/${id}/record`, { method, reference });

const T = "/api/v1/tickets";
export const listTickets = (status?: Ticket["status"]) => apiGet<Ticket[]>(`${T}${status ? `?status=${status}` : ""}`);
export const getTicket = (id: number) => apiGet<Ticket>(`${T}/${id}`);
export const createTicket = (body: { subject: string; body?: string; orderId?: number; priority?: Ticket["priority"] }) => apiPostJson<Ticket>(T, body);
export const changeTicket = (id: number, patch: Partial<{ status: Ticket["status"]; priority: Ticket["priority"]; assignedTo: string }>) => apiPatchJson<Ticket>(`${T}/${id}`, patch);
export const addTicketNote = (id: number, text: string) => apiPostJson<Ticket>(`${T}/${id}/notes`, { text });
