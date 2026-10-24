// Simple inventory (browser side): /api/v1/inventory.

import { apiGet, apiPatchJson, apiPostJson } from "@/lib/api/config";

export type StockItem = {
  id: number;
  sku: string;
  name: string;
  category: string | null;
  costPrice: number | null;
  sellingPrice: number | null;
  stock: number;
  reserved: number;
  available: number;
  reorderThreshold: number;
  supplier: string | null;
  status: "active" | "archived";
  low: boolean;
};
export type StockMovement = { id: number; kind: string; quantity: number; stockDelta: number; reservedDelta: number; orderId: number | null; note: string | null; at: string };
export type NewItem = { sku: string; name: string; category?: string; costPrice?: number; sellingPrice?: number; stock?: number; reorderThreshold?: number; supplier?: string };

const P = "/api/v1/inventory";
export const listStock = (lowOnly = false) => apiGet<StockItem[]>(`${P}/items${lowOnly ? "?lowOnly=true" : ""}`);
export const addStockItem = (body: NewItem) => apiPostJson<StockItem>(`${P}/items`, body);
export const changeStockItem = (id: number, patch: Partial<Pick<StockItem, "name" | "category" | "costPrice" | "sellingPrice" | "reorderThreshold" | "supplier" | "status">>) =>
  apiPatchJson<StockItem>(`${P}/items/${id}`, patch);
export const adjustStock = (id: number, delta: number, kind: "receive" | "adjustment", note?: string) => apiPostJson<StockItem>(`${P}/items/${id}/adjust`, { delta, kind, note });
export const stockMovements = (id: number) => apiGet<StockMovement[]>(`${P}/items/${id}/movements`);
