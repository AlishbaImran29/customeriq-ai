// The Model Report Card (browser side): GET /api/v1/models/report.

import { apiGet } from "@/lib/api/config";

export type ReportRow = {
  model: string;
  label: string;
  decision: "shown" | "hidden";
  reason: string | null;
  metric: string | null;
  modelScore: number | null;
  baselineScore: number | null;
  higherIsBetter: boolean;
  testSize: number | null;
  splitDate: string | null;
};
export type ReportHistoryRow = ReportRow & { createdAt: string };
export type ModelReport = { rows: ReportRow[]; history: ReportHistoryRow[] };

export const getModelReport = () => apiGet<ModelReport>("/api/v1/models/report");

/** 0.8123 -> "0.81"; errors in dollars/units/percent keep two decimals only when small. */
export function scoreText(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return Math.abs(value) >= 100 ? Math.round(value).toLocaleString("en-US") : value.toFixed(2);
}

/** Does the model beat the baseline? null when either score is missing. */
export function beatsBaseline(row: Pick<ReportRow, "modelScore" | "baselineScore" | "higherIsBetter">): boolean | null {
  if (row.modelScore === null || row.baselineScore === null) return null;
  return row.higherIsBetter ? row.modelScore > row.baselineScore : row.modelScore < row.baselineScore;
}
