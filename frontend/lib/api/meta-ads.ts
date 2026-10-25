// Meta Ads (browser side): /api/v1/meta-ads. Test mode is on by default: nothing is sent to Meta until it is switched off on the server.

import { apiGet, apiPostForm, apiPostJson } from "@/lib/api/config";

export type MetaStatus = { testMode: boolean; connected: Record<string, boolean>; readyToSend: boolean; segments: Record<string, string>; setupSteps: string[] };
export type AudienceResult = { segment: string; customers: number; leftOut: number; sample: string[][]; rule?: string; dryRun?: boolean; audienceId?: string | null };
export type MetaEventRow = { id: number; orderId: number; eventId: string; status: string; attempts: number; error: string | null; eventTime: string; sentAt: string | null };
export type RoasCampaign = { campaign: string; spend: number; metaPurchases: number | null; metaRevenue: number | null; orders: number; delivered: number; returned: number; realRevenue: number; enough: boolean; metaRoas: number | null; trueRoas: number | null; costPerDeliveredOrder: number | null };
export type Roas = { start: string; end: string; untaggedOrders: number; minGroupCount: number; campaigns: RoasCampaign[]; note: string };

const P = "/api/v1/meta-ads";
export const metaStatus = () => apiGet<MetaStatus>(`${P}/status`);
export const previewAudience = (segment: string) => apiPostJson<AudienceResult>(`${P}/audiences/preview`, { segment });
export const pushAudience = (segment: string, name: string) => apiPostJson<AudienceResult>(`${P}/audiences/push`, { segment, name, confirm: true });
export const metaEventSummary = () => apiGet<Record<string, number>>(`${P}/events/summary`);
export const listMetaEvents = () => apiGet<MetaEventRow[]>(`${P}/events`);
export const sendMetaEvents = () => apiPostJson<Record<string, number>>(`${P}/events/send`, {});
export const importSpend = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<{ added: number; updated: number; rejected: number; errors: string[] }>(`${P}/ad-spend/import`, form);
};
export const syncSpend = () => apiPostJson<{ rows: number }>(`${P}/ad-spend/sync`, {});
export const getRoas = (start: string, end: string) => apiGet<Roas>(`${P}/roas?start=${start}&end=${end}`);
