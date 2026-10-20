// Season Forecast service (browser side): units to expect per product in each coming season.

import { API_MODE, apiDelete, apiGet, apiPostForm } from "@/lib/api/config";

export const SEASONS_AVAILABLE = API_MODE === "live";

/** Must match MAX_FILE_BYTES in backend/app/api/v1/shipments.py (Vercel accepts bodies of at most 4.5 MB). */
export const MAX_SALES_BYTES = 4 * 1024 * 1024;

export type SeasonWindow = { start: string; end: string };

export type BackTest = {
  /** Past season-years replayed as if live. */
  cases: number;
  /** Product forecasts compared. */
  rows: number;
  tested: string[];
  /** Average error in units. */
  modelMae: number | null;
  baselineMae: number | null;
  /** Average percentage error, 0-1. */
  modelMape: number | null;
  baselineMape: number | null;
  /** 1 - modelMae / baselineMae. */
  improvement: number | null;
  passed: boolean;
};

export type Advice = "stock_more" | "similar" | "stock_less";

export type ProductForecast = {
  product: string;
  /** The baseline: what the same window sold last year. */
  lastYear: number;
  /** null unless the model is proven. */
  forecast: number | null;
  low: number | null;
  high: number | null;
  /** null = the sales are too small to advise. */
  advice: Advice | null;
};

export type Season = {
  id: string;
  name: string;
  status: "forecast" | "last_year_only" | "not_enough_data";
  reason: "not_better" | "no_backtest" | "too_early" | "few_products" | "no_last_year" | "no_target" | null;
  targetYear: number | null;
  window: SeasonWindow | null;
  lastYearWindow: SeasonWindow | null;
  forecastDate: string | null;
  products: number;
  backtest: BackTest;
  rows: ProductForecast[];
};

export type SeasonForecast = {
  /** "real", or "demo" when only made-up data exists. */
  sourceUsed: string;
  realWeeks: number;
  demoWeeks: number;
  dataFrom: string | null;
  dataTo: string | null;
  minGroupCount: number;
  seasons: Season[];
};

export type SalesImportResult = {
  rowsInFile: number;
  weeksCreated: number;
  weeksUpdated: number;
  rejected: number;
  products: number;
  firstWeek: string | null;
  lastWeek: string | null;
  errorCount: number;
  errors: { row: number | null; column: string | null; message: string }[];
  errorsTruncated: boolean;
};

export type SalesSummary = { productWeeks: number; demoProductWeeks: number };

export function getSeasonForecast(): Promise<SeasonForecast> {
  return apiGet<SeasonForecast>("/api/v1/seasons/forecast");
}

export function uploadProductSales(file: File): Promise<SalesImportResult> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<SalesImportResult>("/api/v1/seasons/sales/import", form);
}

export function getSalesSummary(): Promise<SalesSummary> {
  return apiGet<SalesSummary>("/api/v1/seasons/sales/summary");
}

/** DELETE /api/v1/seasons/sales/demo: only the made-up sales; real ones are never touched. */
export function deleteDemoSales(): Promise<{ deleted: number }> {
  return apiDelete<{ deleted: number }>("/api/v1/seasons/sales/demo");
}
