// WhatsApp chat import service (browser side).
//
// The chat file goes to the server, is read in memory and thrown away; the page gets back suggested
// orders to review. Only the orders the seller accepts are sent back to be saved, and they carry no
// chat text. See backend/app/api/v1/whatsapp_import.py.

import { API_MODE, apiDelete, apiGet, apiPostForm, apiPostJson } from "@/lib/api/config";

export const WHATSAPP_IMPORT_AVAILABLE = API_MODE === "live";

/** Must match MAX_CHAT_BYTES in the backend (Vercel accepts bodies of at most 4.5 MB). */
export const MAX_CHAT_BYTES = 4 * 1024 * 1024;

export type DateOrder = "dmy" | "mdy" | "ymd";
export type Confidence = "high" | "medium" | "low";

export type ChatMessage = { sender: string; time: string; text: string };

/** One possible order found in the chat. Only a suggestion: the seller reviews every one. */
export type Candidate = {
  id: number;
  customerName: string;
  /** +923XXXXXXXXX, or null when no number was found. */
  phone: string | null;
  city: string | null;
  amount: number | null;
  otherAmounts: number[];
  paymentType: "cod" | "prepaid" | null;
  /** YYYY-MM-DD */
  orderDate: string;
  /** When the first message of the order was sent (ISO). */
  orderTime: string;
  confidence: Confidence;
  /** What was found, e.g. "Amount and phone found". */
  confidenceLabel: string;
  found: { amount: boolean; phone: boolean; keyword: boolean; city: boolean };
  /** The original messages: shown while reviewing, never saved. */
  messages: ChatMessage[];
};

export type ChatParse = {
  dateOrder: DateOrder;
  /** Every date fits day-first and month-first: ask the seller. */
  dateOrderAmbiguous: boolean;
  senders: { name: string; messages: number }[];
  me: string | null;
  customerNameHint: string | null;
  messageCount: number;
  systemLines: number;
  mediaMessages: number;
  unreadableLines: number;
  candidates: Candidate[];
  truncated: boolean;
};

/** POST /api/v1/whatsapp-import/parse: nothing is saved. */
export function parseChat(file: File, options: { dateOrder?: DateOrder; me?: string } = {}): Promise<ChatParse> {
  const form = new FormData();
  form.append("file", file);
  if (options.dateOrder) form.append("dateOrder", options.dateOrder);
  if (options.me) form.append("me", options.me);
  return apiPostForm<ChatParse>("/api/v1/whatsapp-import/parse", form);
}

/** An accepted order, as sent to be saved. */
export type AcceptedOrder = {
  customerName: string;
  phone: string;
  city: string;
  products: string[];
  amount: number;
  paymentType: string;
  orderDate: string;
  messageTime: string;
};

export type SaveResult = { saved: number; alreadyImported: number; newCustomers: number };

/** POST /api/v1/whatsapp-import/save: all or none. A 422 carries `details.rows` (row number -> field -> message). */
export function saveAccepted(orders: AcceptedOrder[]): Promise<SaveResult> {
  return apiPostJson<SaveResult>("/api/v1/whatsapp-import/save", { orders });
}

export type WhatsAppSummary = { orders: number; customers: number };

export function getWhatsAppSummary(): Promise<WhatsAppSummary> {
  return apiGet<WhatsAppSummary>("/api/v1/whatsapp-import/summary");
}

export type DeleteResult = { ordersDeleted: number; customersDeleted: number };

/** DELETE /api/v1/whatsapp-import: every order imported from a chat, and customers left with no orders. */
export function deleteWhatsAppData(): Promise<DeleteResult> {
  return apiDelete<DeleteResult>("/api/v1/whatsapp-import");
}
