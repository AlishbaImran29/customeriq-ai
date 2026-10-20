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
  /** COD money: days from delivery to payment. null without enough fully paid parcels. */
  averageDaysToPay: number | null;
  paidParcels: number;
};

export type ReturnAlert = {
  courier: string;
  city: string;
  returned: number;
  closed: number;
  rate: number;
  othersReturned: number;
  othersClosed: number;
  othersRate: number;
  pValue: number;
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
  /** Unusually high return rates; both groups passed the minimum count. */
  alerts: ReturnAlert[];
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

export type CourierSuggestion = {
  city: string;
  /** false = no courier has enough history in this city. */
  available: boolean;
  /** "demo" when the history is made up. */
  sourceUsed: string;
  best: CourierStats | null;
  others: CourierStats[];
};

/** GET /api/v1/couriers/suggest: the courier with the fewest returns in a city, only if its history is long enough. */
export function getCourierSuggestion(city: string): Promise<CourierSuggestion | null> {
  return apiGet<CourierSuggestion | null>(`/api/v1/couriers/suggest?city=${encodeURIComponent(city)}`);
}
