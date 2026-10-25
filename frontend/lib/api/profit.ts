// Profit analytics (browser side): /api/v1/profit.

import { apiDelete, apiGet, apiPostJson, apiPutJson } from "@/lib/api/config";

export type GroupBy = "channel" | "city" | "courier" | "product" | "customer";
export type ProfitGroup = { key: string; orders: number; revenue: number; profit: number; enough: boolean; margin: number | null; profitPerOrder: number | null; returnRate: number | null };
export type ProfitSummary = {
  start: string;
  end: string;
  minGroupCount: number;
  orders: { placed: number; ended: number; pending: number; counted: number; costUnknown: number };
  money: { grossRevenue: number; deliveredRevenue: number; prepaidCollected: number; adSpend: number; estimatedProfit: number | null };
  rates: { returnRate: number | null; failedDeliveryRate: number | null; repeatPurchaseRate: number | null };
  lowStockItems: number;
  missing: Record<string, number>;
  packingSet: boolean;
  returnShippingSet: boolean;
  revenueByChannel: Record<string, number>;
  groups: Record<GroupBy, ProfitGroup[]>;
  definitions: { name: string; formula: string }[];
  note: string;
};
export type CostSettings = { packingCost: number | null; returnShippingCost: number | null };
export type AdSpendRow = { id: number; spendDate: string; channel: string; campaign: string | null; amount: number; source: string };

const P = "/api/v1/profit";
export const getProfit = (start: string, end: string) => apiGet<ProfitSummary>(`${P}/summary?start=${start}&end=${end}`);
export const getCostSettings = () => apiGet<CostSettings>(`${P}/settings`);
export const saveCostSettings = (s: CostSettings) => apiPutJson<CostSettings>(`${P}/settings`, s);
export const listAdSpend = () => apiGet<AdSpendRow[]>(`${P}/ad-spend`);
export const addAdSpend = (body: { spendDate: string; channel: string; amount: number; campaign?: string }) => apiPostJson<AdSpendRow>(`${P}/ad-spend`, body);
export const deleteAdSpend = (id: number) => apiDelete<void>(`${P}/ad-spend/${id}`);
