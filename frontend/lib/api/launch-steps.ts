// Launch Studio steps 2-6 (browser side): vendors and quotes, competitor ads, creatives, profit check, launch results.

import { apiDelete, apiGet, apiPatchJson, apiPostForm, apiPostJson, apiPutJson } from "@/lib/api/config";

export type Language = "ur" | "roman_ur" | "en";

export type Vendor = {
  id: number;
  name: string;
  /** +92XXXXXXXXXX */
  whatsappPhone: string | null;
  city: string | null;
  categories: string | null;
  notes: string | null;
  quality: { projects: number; closedOrders: number; returnRate: number | null; needed: number };
};
export type VendorInput = { name: string; whatsappPhone?: string; city?: string; categories?: string; notes?: string };

export type Quote = {
  id: number;
  vendorId: number;
  vendorName: string;
  launchProjectId: number;
  unitPrice: number;
  moq: number | null;
  deliveryDays: number | null;
  qualityNotes: string | null;
  sampleReceived: boolean;
  quotedOn: string;
  cheapest: boolean;
  fastest: boolean;
  chosen: boolean;
};
export type QuoteInput = {
  vendorId: number;
  unitPrice: number;
  moq?: number;
  deliveryDays?: number;
  qualityNotes?: string;
  sampleReceived?: boolean;
};

export type QuoteMessage = { label: "AI suggestion"; message: string; whatsappPhone: string | null; cached: boolean; model: string | null };

export type Ad = {
  id: number;
  launchProjectId: number;
  pageName: string;
  adText: string | null;
  link: string | null;
  priceSeen: number | null;
  offerSeen: string | null;
  dateSeen: string;
  /** A link that expires after an hour. */
  screenshotUrl: string | null;
  hasScreenshot: boolean;
};
export type AdAnalysis = {
  label: "AI suggestion";
  ads: { id: number; hookType: string; offer: string | null; price: number | null; cta: string | null; codMentioned: boolean; language: string }[];
  patterns: string[];
  gaps: string[];
  cached: boolean;
  model: string | null;
};

export type Angle = "price" | "quality" | "urgency" | "social_proof" | "cod_trust";
export const ANGLES: Angle[] = ["price", "quality", "urgency", "social_proof", "cod_trust"];
/** Field names are the ones the backend saves (snake_case inside the saved content). */
export type MetaAd = { hook: string; primary_text: string; headline: string; cta: string; angle: Angle };
export type InstagramPost = { caption: string; hashtags: string[] };
export type CreativeKind = "meta_ad" | "instagram" | "whatsapp_status";
export type Brief = {
  productName: string;
  features: string[];
  price?: number;
  offer?: string;
  targetCustomer?: string;
  language: Language;
  tone: string;
};
export type Creatives = {
  label: "AI suggestion";
  metaAds: MetaAd[];
  instagram: InstagramPost | null;
  whatsappStatus: { text: string } | null;
  /** Suggestions dropped because they made claims that cannot be proven. */
  removed: number;
  usedCompetitorAnalysis: boolean;
  cached: boolean;
  model: string | null;
};
export type SavedCreative = { id: number; launchProjectId: number; kind: CreativeKind; content: Record<string, unknown>; aiGenerated: boolean; createdAt: string };

export type ProfitInput = { cost: number; price: number; packing: number; courierFee: number; returnShipping: number; returnRate: number; adBudget: number };
export type ProfitResult = {
  label: "Estimate from your numbers";
  profitDelivered: number;
  lossReturned: number;
  profitPerOrderPlaced: number;
  margin: number | null;
  breakEvenCostPerPurchase: number | null;
  breakEvenRoas: number | null;
  ordersToRecoverBudget: number | null;
  warnings: string[];
};
export type ProfitDefaults = {
  cost: number | null;
  costSource: string | null;
  returnRate: number | null;
  returnRateOrders: number;
  returnRateNeeded: number;
  saved: ProfitInput | null;
};

export type Results = {
  launchedOn: string | null;
  linkedProducts: string[];
  orders: number;
  revenue: number;
  customers: number;
  repeatBuyers: number;
  closedOrders: number;
  returnRate: number | null;
  returnNeeded: number;
  realProfitPerOrder: number | null;
  expectedProfitPerOrder: number | null;
  hasProfitInputs: boolean;
  minGroupCount: number;
  reason: "not_launched" | "no_products" | null;
};

const P = "/api/v1/launch";

export const listVendors = () => apiGet<Vendor[]>(`${P}/vendors`);
export const addVendor = (body: VendorInput) => apiPostJson<Vendor>(`${P}/vendors`, body);
export const editVendor = (id: number, body: Partial<VendorInput>) => apiPatchJson<Vendor>(`${P}/vendors/${id}`, body);
export const removeVendor = (id: number) => apiDelete<void>(`${P}/vendors/${id}`);

export const listQuotes = (projectId: number) => apiGet<Quote[]>(`${P}/projects/${projectId}/quotes`);
export const addQuote = (projectId: number, body: QuoteInput) => apiPostJson<Quote[]>(`${P}/projects/${projectId}/quotes`, body);
export const removeQuote = (id: number) => apiDelete<Quote[]>(`${P}/quotes/${id}`);
export const chooseVendor = (projectId: number, vendorId: number | null) =>
  apiPutJson<Quote[]>(`${P}/projects/${projectId}/vendor`, { vendorId });
export const requestQuote = (vendorId: number, body: { projectId: number; quantity: number; language: Language; force?: boolean }) =>
  apiPostJson<QuoteMessage>(`${P}/vendors/${vendorId}/quote-request`, body);

export const adLibraryLink = (keyword: string) => apiGet<{ url: string }>(`${P}/ad-library-link?keyword=${encodeURIComponent(keyword)}`);
export const listAds = (projectId: number) => apiGet<Ad[]>(`${P}/projects/${projectId}/ads`);
export const saveAd = (projectId: number, form: FormData) => apiPostForm<Ad>(`${P}/projects/${projectId}/ads`, form);
export const removeAd = (id: number) => apiDelete<void>(`${P}/ads/${id}`);
export const analyseAds = (projectId: number, force: boolean) => apiPostJson<AdAnalysis>(`${P}/projects/${projectId}/ads/analyse`, { force });

export const generateCreatives = (projectId: number, brief: Brief, force: boolean) =>
  apiPostJson<Creatives>(`${P}/projects/${projectId}/creatives/generate`, { ...brief, force });
export const regenerateCreative = (projectId: number, kind: CreativeKind, brief: Brief, current: unknown) =>
  apiPostJson<{ kind: CreativeKind; content: Record<string, unknown>; model: string | null }>(`${P}/projects/${projectId}/creatives/regenerate`, { kind, brief, current });
export const listCreatives = (projectId: number) => apiGet<SavedCreative[]>(`${P}/projects/${projectId}/creatives`);
export const saveCreative = (projectId: number, kind: CreativeKind, content: Record<string, unknown>, aiGenerated: boolean) =>
  apiPostJson<SavedCreative>(`${P}/projects/${projectId}/creatives`, { kind, content, aiGenerated });
export const editCreative = (id: number, content: Record<string, unknown>) => apiPatchJson<SavedCreative>(`${P}/creatives/${id}`, { content });
export const removeCreative = (id: number) => apiDelete<void>(`${P}/creatives/${id}`);

export const calculateProfit = (body: ProfitInput) => apiPostJson<ProfitResult>(`${P}/profit/calculate`, body);
export const saveProfit = (projectId: number, body: ProfitInput) => apiPutJson<ProfitResult>(`${P}/projects/${projectId}/profit`, body);
export const getProfitDefaults = (projectId: number) => apiGet<ProfitDefaults>(`${P}/projects/${projectId}/profit-defaults`);

export const markLaunched = (projectId: number, launchedOn?: string) =>
  apiPostJson<{ status: string; launchedOn: string }>(`${P}/projects/${projectId}/launch`, { launchedOn });
export const listLinked = (projectId: number) => apiGet<{ id: number; name: string }[]>(`${P}/projects/${projectId}/products`);
export const linkProduct = (projectId: number, name: string) => apiPostJson<{ id: number; name: string }[]>(`${P}/projects/${projectId}/products`, { name });
export const unlinkProduct = (projectId: number, linkId: number) => apiDelete<{ id: number; name: string }[]>(`${P}/projects/${projectId}/products/${linkId}`);
export const searchProductNames = (q: string) => apiGet<{ name: string }[]>(`${P}/product-names?q=${encodeURIComponent(q)}`);
export const getResults = (projectId: number) => apiGet<Results>(`${P}/projects/${projectId}/results`);
