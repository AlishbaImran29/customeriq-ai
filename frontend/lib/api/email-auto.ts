import { apiGet, apiPostJson, apiPutJson } from "@/lib/api/config";

const P = "/api/v1/email-auto";

export type CodEmailStatus = "pending" | "confirmed" | "cancelled";

export type CodEmailRow = {
  orderId: number;
  orderNumber: string;
  customerName: string;
  email: string | null;
  amount: number;
  status: CodEmailStatus;
  sentAt: string | null;
  reminderSentAt: string | null;
  answeredAt: string | null;
};

export type AnnouncementRow = { id: number; productName: string; category: string | null; status: "draft" | "sent"; sentCount: number };

export type EmailSettings = {
  storeName: string;
  logoUrl: string;
  brandColor: string;
  supportEmail: string;
  storeUrl: string;
  effective: { storeName: string; brandColor: string; supportEmail: string | null };
};

export type EmailOverview = {
  sentToday: number;
  dailyLimit: number;
  marketingCap: number;
  testMode: boolean;
  senderEmail: string | null;
  linksReady: boolean;
  cod: CodEmailRow[];
  announcements: AnnouncementRow[];
  lifecycle: Record<string, number>;
  settings: EmailSettings;
};

export type BulkResult = { sent: number; failed: number; skipped: Record<string, number>; remaining: number; message: string | null; testMode: boolean };
export type Preview = { key: string; label: string; subject: string; html: string; text: string };
export type AnnouncementPreview = { id: number; status: string; subject: string; html: string; text: string; audience: { sameCategory: number; others: number; leftOut: number } };

export type AnnounceInput = { name: string; category?: string; price?: number; description?: string; imageUrl?: string; productUrl?: string };

export const getOverview = () => apiGet<EmailOverview>(`${P}/overview`);
export const getPreviews = () => apiGet<Preview[]>(`${P}/previews`);
export const saveSettings = (s: Omit<EmailSettings, "effective">) => apiPutJson<EmailSettings>(`${P}/settings`, s);
export const sendCod = (orderId: number, reminder: boolean) => apiPostJson<{ status: CodEmailStatus; testMode: boolean }>(`${P}/cod/${orderId}/send?reminder=${reminder}`, {});
export const refreshLifecycle = () => apiPostJson<Record<string, number>>(`${P}/lifecycle/refresh`, {});
export const sendWinback = (discountCode: string, discountValue: string) => apiPostJson<BulkResult>(`${P}/winback/send`, { discountCode, discountValue });
export const createAnnouncement = (body: AnnounceInput) => apiPostJson<{ id: number }>(`${P}/announcements`, body);
export const getAnnouncementPreview = (id: number) => apiGet<AnnouncementPreview>(`${P}/announcements/${id}/preview`);
export const sendAnnouncement = (id: number) => apiPostJson<BulkResult>(`${P}/announcements/${id}/send`, {});
export const loadSampleData = () => apiPostJson<{ created: number }>(`${P}/mock/load`, {});
export const sendTestEmails = () => apiPostJson<{ results: { subject: string; status: string; error: string | null }[]; testMode: boolean }>(`${P}/test-send`, {});
