// Auto Messenger service (browser side): settings, templates, consent, messages, order status, customer videos,
// campaigns, journeys and results. The server checks consent, approval, quiet hours and the weekly cap; this file only talks to it.

import { API_MODE, apiDelete, apiGet, apiPatchJson, apiPostForm, apiPostJson, apiPutJson } from "@/lib/api/config";

export const MESSENGER_AVAILABLE = API_MODE === "live";

export type Channel = "whatsapp" | "email";
export type Category = "utility" | "marketing";
export type Lang = "ur" | "en";
export type MetaStatus = "not_submitted" | "pending" | "approved" | "rejected";
export type MessageStatus = "queued" | "sent" | "delivered" | "read" | "failed" | "replied" | "skipped";
export type OrderStatus = "confirmed" | "dispatched" | "in_transit" | "out_for_delivery" | "delivered" | "returned";
export const ORDER_STATUSES: OrderStatus[] = ["confirmed", "dispatched", "in_transit", "out_for_delivery", "delivered", "returned"];

const P = "/api/v1/messaging";

// --- settings -------------------------------------------------------------------------------------------------------

export type Connection = { configured: boolean; details: Record<string, boolean>; provider?: string | null };
export type ConsentCount = { optedIn: number; optedOut: number; notAsked: number };

export type MessengerSettings = {
  dryRun: boolean;
  dryRunForced: boolean;
  effectiveDryRun: boolean;
  quietStart: string;
  quietEnd: string;
  timezone: string;
  weeklyMarketingCap: number;
  defaultLanguage: Lang;
  storeName: string | null;
  reviewUrl: string | null;
  costUtility: number | null;
  costMarketing: number | null;
  campaignBatchSize: number;
  earlyAccessHours: number;
  holdoutPercent: number;
  whatsapp: Connection;
  email: Connection;
  unsubscribeReady: boolean;
  webhookUrl: string | null;
  consent: Record<Channel, ConsentCount>;
  development: boolean;
  schedulerReady: boolean;
  shopifyReady: boolean;
};

export type SettingsPatch = Partial<{
  dryRun: boolean;
  quietStart: string;
  quietEnd: string;
  weeklyMarketingCap: number;
  defaultLanguage: Lang;
  storeName: string;
  reviewUrl: string;
  costUtility: number | null;
  costMarketing: number | null;
  campaignBatchSize: number;
  earlyAccessHours: number;
  holdoutPercent: number;
}>;

export const getSettings = () => apiGet<MessengerSettings>(`${P}/settings`);
export const saveSettings = (patch: SettingsPatch) => apiPutJson<MessengerSettings>(`${P}/settings`, patch);
export const testSend = (body: { channel: Channel; to?: string; language: Lang }) =>
  apiPostJson<{ ok: boolean; dryRun: boolean; error: string | null; sentTo: string }>(`${P}/test-send`, body);
export const runDueNow = () => apiPostJson<Record<string, Record<string, number>>>(`${P}/run-due`, {});
export const processQueue = () => apiPostJson<{ processed: number; sent: number; requeued: number; failed: number; skipped: number }>(`${P}/process-queue`, {});

// --- templates -------------------------------------------------------------------------------------------------------

export type Template = {
  id: number;
  name: string;
  channel: Channel;
  category: Category;
  language: Lang;
  event: string | null;
  subject: string | null;
  body: string;
  variables: string[];
  metaTemplateName: string | null;
  metaApprovalStatus: MetaStatus;
  approvedBySeller: boolean;
  approvedAt: string | null;
  isDefault: boolean;
};
export type TemplateInput = { name: string; channel: Channel; category: Category; language: Lang; event?: string; subject?: string; body: string; metaTemplateName?: string };
export type TemplatePatch = Partial<Omit<TemplateInput, "channel" | "language"> & { metaApprovalStatus: MetaStatus }>;
export type Variable = { name: string; description: string; optional: boolean };
export type Preview = { label: string; text: string | null; subject: string | null; variables: string[]; metaBody: string; metaVariables: string[]; error: string | null };

export const listTemplates = (channel?: Channel) => apiGet<Template[]>(`${P}/templates${channel ? `?channel=${channel}` : ""}`);
export const listVariables = () => apiGet<Variable[]>(`${P}/variables`);
export const createTemplate = (body: TemplateInput) => apiPostJson<Template>(`${P}/templates`, body);
export const editTemplate = (id: number, patch: TemplatePatch) => apiPatchJson<Template>(`${P}/templates/${id}`, patch);
export const approveTemplate = (id: number) => apiPostJson<Template>(`${P}/templates/${id}/approve`, {});
export const unapproveTemplate = (id: number) => apiPostJson<Template>(`${P}/templates/${id}/unapprove`, {});
export const deleteTemplate = (id: number) => apiDelete<void>(`${P}/templates/${id}`);
export const previewTemplate = (body: { body: string; subject?: string; language: Lang }) => apiPostJson<Preview>(`${P}/templates/preview`, body);
export const seedTemplates = (groups: ("orders" | "followups" | "journeys")[]) => apiPostJson<{ added: number }>(`${P}/templates/seed-defaults`, { groups });

// --- consent ----------------------------------------------------------------------------------------------------------

export type ConsentState = "opted_in" | "opted_out" | "none";
export type ChannelConsent = { state: ConsentState; changedOn: string | null; source: string | null };
export type ConsentCustomer = { id: number; name: string; phone: string | null; email: string | null; whatsapp: ChannelConsent; emailConsent: ChannelConsent };
export type ConsentPage = { total: number; customers: ConsentCustomer[] };
export type ConsentImportResult = { rowsInFile: number; changed: number; unchanged: number; notFound: number; rejected: number; errors: { row: number | null; column: string | null; message: string }[] };

export function listConsent(q: { search?: string; channel?: Channel; state?: ConsentState; offset?: number }) {
  const params = new URLSearchParams();
  if (q.search) params.set("search", q.search);
  if (q.channel && q.state) {
    params.set("channel", q.channel);
    params.set("state", q.state);
  }
  if (q.offset) params.set("offset", String(q.offset));
  return apiGet<ConsentPage>(`${P}/consent?${params}`);
}
export const changeConsent = (customerId: number, body: { channel: Channel; optedIn: boolean; note?: string }) => apiPatchJson<ConsentCustomer>(`${P}/consent/${customerId}`, body);
export const consentHistory = (customerId: number) => apiGet<{ channel: Channel; action: string; source: string; note: string | null; at: string }[]>(`${P}/consent/${customerId}/history`);
export function importConsent(file: File, confirm: boolean) {
  const form = new FormData();
  form.append("file", file);
  form.append("confirm", confirm ? "true" : "false");
  return apiPostForm<ConsentImportResult>(`${P}/consent/import`, form);
}

// --- messages -----------------------------------------------------------------------------------------------------------

export type MessageRow = {
  id: number;
  customerId: number;
  customerName: string;
  channel: Channel;
  category: Category;
  subject: string | null;
  text: string;
  status: MessageStatus;
  error: string | null;
  attempts: number;
  dryRun: boolean;
  templateName: string | null;
  campaignId: number | null;
  journeyId: number | null;
  orderId: number | null;
  queuedAt: string;
  sentAt: string | null;
  nextAttemptAt: string | null;
};
export type IncomingRow = { id: number; customerName: string | null; fromAddress: string; messageType: string; body: string | null; isStop: boolean; answer: string | null; receivedAt: string };

export const listMessages = (status?: MessageStatus, channel?: Channel) => {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (channel) params.set("channel", channel);
  return apiGet<MessageRow[]>(`${P}/messages?${params}`);
};
export const listIncoming = () => apiGet<IncomingRow[]>(`${P}/incoming`);
export const simulateIncoming = (phone: string, text: string) => apiPostJson<Record<string, number>>(`${P}/dev/simulate-incoming`, { phone, text });

// --- order status -------------------------------------------------------------------------------------------------------------

export type OrderRow = {
  id: number;
  orderNumber: string;
  customerId: number;
  customerName: string;
  phone: string | null;
  amount: number;
  paymentType: string | null;
  products: string | null;
  status: OrderStatus | null;
  statusAt: string | null;
  messages: number;
};
export type StatusResult = { recorded: boolean; announced: boolean; reason: string | null; messages: MessageRow[] };
export type Timeline = { orderNumber: string; customerName: string; events: { status: OrderStatus; at: string; source: string; courier: string | null; trackingNumber: string | null; note: string | null }[]; messages: MessageRow[] };

export const listOrders = (search?: string) => apiGet<OrderRow[]>(`${P}/orders${search ? `?search=${encodeURIComponent(search)}` : ""}`);
export const changeOrderStatus = (id: number, body: { status: OrderStatus; courier?: string; trackingNumber?: string; note?: string; notify: boolean }) =>
  apiPostJson<StatusResult>(`${P}/orders/${id}/status`, body);
export const orderTimeline = (id: number) => apiGet<Timeline>(`${P}/orders/${id}/timeline`);

// --- customer videos ------------------------------------------------------------------------------------------------------------

export type MediaRow = {
  id: number;
  customerName: string;
  orderNumber: string | null;
  kind: "image" | "video";
  mimeType: string | null;
  sizeBytes: number | null;
  status: "pending" | "stored" | "rejected" | "failed";
  error: string | null;
  questionSent: boolean;
  shareAnswer: "pending" | "yes" | "no";
  usableInAds: boolean;
  receivedAt: string;
  url: string | null;
};
export type MediaFilter = "all" | "waiting" | "yes" | "no" | "usable" | "rejected";

export const listMedia = (show: MediaFilter) => apiGet<MediaRow[]>(`${P}/media?show=${show}`);
export const setMediaUsable = (id: number, usable: boolean) => apiPostJson<MediaRow>(`${P}/media/${id}/usable`, { usable });
export const deleteMedia = (id: number) => apiDelete<void>(`${P}/media/${id}`);
export const processMedia = () => apiPostJson<{ stored: number; rejected: number; failed: number; waiting: number }>(`${P}/media/process`, {});

// --- products and campaigns -----------------------------------------------------------------------------------------------------

export const SEGMENTS = ["Champions", "Loyal Customers", "Potential Loyalists", "At-Risk Customers", "Lost Customers"] as const;
export type Segment = (typeof SEGMENTS)[number];

export type Product = { id: number; name: string; category: string | null; price: number | null; description: string | null; source: string; campaignId: number | null };
export type AudienceConfig = { categories: string[]; segments: Segment[]; includeCategoryBuyers: boolean };
export type SegmentMessage = { en: string; ur: string };
export type CampaignMessages = { messages: Record<string, SegmentMessage>; subject: SegmentMessage };
export type Campaign = {
  id: number;
  name: string;
  status: "draft" | "approved" | "sending" | "completed" | "cancelled";
  productId: number | null;
  productName: string | null;
  audience: AudienceConfig;
  offerText: string | null;
  earlyAccessHours: number;
  messages: CampaignMessages | null;
  aiDraft: boolean;
  approvedAt: string | null;
  completedAt: string | null;
  counts: { pending: number; sent: number; skipped: number; total: number };
  createdAt: string;
};
export type AudienceSummary = { candidates: number; eligible: number; noConsent: number; noAddress: number; bySegment: Record<string, number>; truncated: boolean };
export type Sample = { customerName: string; segment: string; channel: Channel; language: Lang; text: string | null; subject: string | null; error: string | null };
export type CampaignPreview = { label: string; audience: AudienceSummary; samples: Sample[] };
export type Recipient = { id: number; customerName: string; segment: string; stage: "early" | "regular"; scheduledFor: string; status: "pending" | "sent" | "skipped"; reason: string | null; messageStatus: string | null };

export const listProducts = () => apiGet<Product[]>(`${P}/products`);
export const addProduct = (body: { name: string; category?: string; price?: number; description?: string }) => apiPostJson<Product>(`${P}/products`, body);
export const productFromLaunch = (projectId: number) => apiPostJson<Product>(`${P}/products/from-launch/${projectId}`, {});
export const listCampaigns = () => apiGet<Campaign[]>(`${P}/campaigns`);
export const getCampaign = (id: number) => apiGet<Campaign>(`${P}/campaigns/${id}`);
export const editCampaign = (id: number, patch: Partial<{ name: string; audience: AudienceConfig; offerText: string; earlyAccessHours: number }>) => apiPatchJson<Campaign>(`${P}/campaigns/${id}`, patch);
export const previewCampaign = (id: number) => apiGet<CampaignPreview>(`${P}/campaigns/${id}/preview`);
export const generateCampaign = (id: number, force: boolean) => apiPostJson<{ label: "AI draft"; campaign: Campaign; cached: boolean; model: string | null }>(`${P}/campaigns/${id}/generate`, { force });
export const saveCampaignMessages = (id: number, body: CampaignMessages) => apiPutJson<Campaign>(`${P}/campaigns/${id}/messages`, body);
export const approveCampaign = (id: number) => apiPostJson<{ recipients: number; early: number }>(`${P}/campaigns/${id}/approve`, {});
export const cancelCampaign = (id: number) => apiPostJson<{ stopped: number }>(`${P}/campaigns/${id}/cancel`, {});
export const deleteCampaign = (id: number) => apiDelete<void>(`${P}/campaigns/${id}`);
export const listRecipients = (id: number) => apiGet<Recipient[]>(`${P}/campaigns/${id}/recipients`);

// --- journeys --------------------------------------------------------------------------------------------------------------------

export type Step = { day: number; event: string };
export type Journey = {
  id: number;
  key: string;
  name: string;
  description: string | null;
  triggerSegment: string;
  anchor: "enrollment" | "first_order";
  steps: Step[];
  loopEveryDays: number | null;
  maxSends: number | null;
  maxPer30Days: number | null;
  graceDays: number;
  enabled: boolean;
  counts: { active: number; holdout: number; completed: number; stopped: Record<string, number> };
  messagesSent: number;
  templatesReady: boolean;
};
export type JourneyPatch = Partial<{ name: string; description: string; enabled: boolean; anchor: "enrollment" | "first_order"; steps: Step[]; loopEveryDays: number | null; maxSends: number | null; maxPer30Days: number | null; graceDays: number }>;

export const listJourneys = () => apiGet<Journey[]>(`${P}/journeys`);
export const seedJourneys = () => apiPostJson<{ journeys: number; templates: number }>(`${P}/journeys/seed-defaults`, {});
export const editJourney = (id: number, patch: JourneyPatch) => apiPatchJson<Journey>(`${P}/journeys/${id}`, patch);
export const runJourneysNow = () => apiPostJson<Record<string, number>>(`${P}/journeys/run-now`, {});

// --- results ------------------------------------------------------------------------------------------------------------------------

export type Group = { id: number | null; name: string; sent: number; delivered: number; read: number; replied: number; failed: number; skipped: number; optOuts: number; orders: number; revenue: number; whatsappCost: number | null };
export type Comparison = {
  enough: boolean;
  messaged: number;
  holdout: number;
  needed: number;
  messagedRate: number | null;
  holdoutRate: number | null;
  difference: number | null;
  low: number | null;
  high: number | null;
  couldBeChance: boolean | null;
  messagedRevenue: number | null;
  holdoutRevenue: number | null;
  reason: string | null;
};
export type MessengerResults = {
  days: number;
  includeDryRun: boolean;
  minGroupCount: number;
  totals: { sent: number; delivered: number; read: number; replied: number; failed: number; skipped: number; optOuts: number; orders: number; revenue: number };
  cost: { utilityMessages: number; marketingMessages: number; utilityRate: number | null; marketingRate: number | null; total: number | null };
  templates: Group[];
  campaigns: Group[];
  journeys: { journeyId: number; name: string; enabled: boolean; group: Group | null; comparison: Comparison }[];
};

export const getResults = (days: number, includeDryRun: boolean) => apiGet<MessengerResults>(`${P}/results?days=${days}&includeDryRun=${includeDryRun}`);
