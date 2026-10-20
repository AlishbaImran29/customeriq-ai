// Courier Scorecard service (browser side): how each courier did in each city.

import { API_MODE, apiGet } from "@/lib/api/config";

export const SCORECARD_AVAILABLE = API_MODE === "live";

export type CourierStats = {
  courier: string;
  /** null = the shipments had no city. */
  city: string | null;
  shipments: number;
  /** Delivered + returned: the parcels a rate is worked out from. */
  closed: number;
  delivered: number;
  returned: number;
  lost: number;
  inTransit: number;
  refused: number;
  /** 0-1. null when there are fewer closed parcels than the minimum: no number is shown then. */
  deliveryRate: number | null;
  returnRate: number | null;
  averageDays: number | null;
  enough: boolean;
  /** How many more closed parcels are needed before the rates appear. */
  needed: number;
};

export type Scorecard = {
  sourceRequested: string;
  /** What the figures are made of: "real", "demo" or "all". */
  sourceUsed: string;
  realShipments: number;
  demoShipments: number;
  minGroupCount: number;
  periodDays: number | null;
  periodStart: string | null;
  periodEnd: string | null;
  shipments: number;
  couriers: CourierStats[];
  rows: CourierStats[];
  allCouriers: string[];
  allCities: string[];
};

export type ScorecardQuery = { source: string; days: number | null; city: string; courier: string };

/** GET /api/v1/couriers/scorecard */
export function getScorecard(q: ScorecardQuery): Promise<Scorecard> {
  const params = new URLSearchParams({ source: q.source });
  if (q.days) params.set("days", String(q.days));
  if (q.city) params.set("city", q.city);
  if (q.courier) params.set("courier", q.courier);
  return apiGet<Scorecard>(`/api/v1/couriers/scorecard?${params}`);
}
