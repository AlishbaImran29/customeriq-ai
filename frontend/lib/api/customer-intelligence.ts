// Customer intelligence service layer (server-only: used by Server Components).
//
// Demo mode (no NEXT_PUBLIC_API_BASE_URL): returns clearly labelled sample data
// from `lib/mock`. Live mode: calls the FastAPI endpoints and maps the response.
// A failed live request throws ApiError — it never falls back to sample data.

import type { DateRange } from "@/lib/dates";
import "server-only";
import { connection } from "next/server";
import { API_MODE, ApiError, apiGet } from "@/lib/api/config";
import * as mock from "@/lib/mock/customer-intelligence";
import { serverAccessToken } from "@/lib/supabase/server";
import { withSegmentMeta } from "@/lib/segments";
import type {
  Customer,
  DataMeta,
  ExecutiveSummary,
  GrowthScoreDetails,
  Kpis,
  ModelInfo,
  OrderRiskOverview,
  Recommendation,
  RevenueAtRiskPoint,
  RevenueDriverGroup,
  RevenuePoint,
  RiskBucket,
  SegmentName,
  SegmentStats,
  SegmentSummary,
  ShareRow,
} from "@/lib/types";

// Sample predictions in demo mode are part of the made-up sample data.
const DEMO_MODEL: ModelInfo = { status: "available", reason: null, metrics: [] };

const DEMO_META: DataMeta = {
  source: "demo",
  asOf: null,
  customerCount: mock.kpis.totalCustomers ?? 0,
  segmented: true,
  models: { churn: DEMO_MODEL },
  unavailable: [],
};

/**
 * Live requests run per request (never at build time) and carry the visitor's
 * sign-in token to the backend.
 */
async function live<T>(path: string): Promise<T> {
  await connection();
  const token = await serverAccessToken();
  return apiGet<T>(path, { cache: "no-store", headers: token ? { Authorization: `Bearer ${token}` } : undefined });
}

const byChurnDesc = (a: Customer, b: Customer) =>
  (b.churnProbability ?? 0) - (a.churnProbability ?? 0);

// --- Overview -------------------------------------------------------------

export type Overview = {
  /** Live data only: the breakdown behind the Growth Score. */
  growthScoreDetails: GrowthScoreDetails | null;
  meta: DataMeta;
  kpis: Kpis;
  kpiDeltas: Kpis;
  executiveSummary: ExecutiveSummary;
  revenueSeries: RevenuePoint[];
  segments: SegmentSummary[];
  topRecommendations: Recommendation[];
  atRiskCustomers: Customer[];
  /** The sales channel the figures are limited to; null = all channels. */
  channel: string | null;
  /** More customers needed before customers can be segmented (0 when there are enough). */
  segmentsNeeded: number;
};

type OverviewResponse = Omit<Overview, "segments"> & { segments: SegmentStats[] };

/** GET /api/v1/dashboard/overview (optionally for a chosen period; default: the last 90 days of data) */
export async function getOverview(range?: DateRange, channel?: string): Promise<Overview> {
  if (API_MODE === "demo") {
    return {
      meta: DEMO_META,
      kpis: mock.kpis,
      kpiDeltas: mock.kpiDeltas,
      executiveSummary: { ...mock.executiveSummary, method: "sample" },
      revenueSeries: mock.revenueSeries,
      segments: mock.segmentSummary,
      topRecommendations: mock.recommendations.filter((i) => i.impact === "High").slice(0, 3),
      atRiskCustomers: [...mock.customers].sort(byChurnDesc).slice(0, 4),
      growthScoreDetails: null,
      channel: null,
      segmentsNeeded: 0,
    };
  }
  const parts = [range ? `start=${range.from}&end=${range.to}` : "", channel ? `channel=${encodeURIComponent(channel)}` : ""];
  const query = parts.some(Boolean) ? `?${parts.filter(Boolean).join("&")}` : "";
  const data = await live<OverviewResponse>(`/api/v1/dashboard/overview${query}`);
  return { ...data, segments: withSegmentMeta(data.segments) };
}

// --- Cohort retention -----------------------------------------------------------

export type CohortRow = {
  label: string;
  size: number;
  /** % of the cohort that ordered in month 0, 1, 2...; null where not measurable yet. */
  retention: (number | null)[];
};

export type CohortOverview = {
  meta: DataMeta;
  cohorts: CohortRow[];
  averages: (number | null)[];
  months: number;
  /** The month still in progress (left out of the comparison), if any. */
  partialMonth: string | null;
};

/** GET /api/v1/cohorts (live data only: there is no sample cohort data) */
export async function getCohorts(): Promise<CohortOverview> {
  if (API_MODE === "demo") {
    return { meta: DEMO_META, cohorts: [], averages: [], months: 12, partialMonth: null };
  }
  return live<CohortOverview>("/api/v1/cohorts");
}

// --- One customer ----------------------------------------------------------------

export type CustomerOrder = { orderDate: string; value: number; category: string | null; channel: string | null };

export type CustomerDetail = {
  meta: DataMeta;
  customer: Customer;
  firstOrder: string | null;
  averageOrderValue: number | null;
  averageDaysBetweenOrders: number | null;
  /** Why the churn risk is what it is (top 3); empty when the churn model is not available. */
  churnReasons?: { template: string; params: Record<string, string>; text: string }[];
  ordersTotal: number;
  /** Newest first, capped; `ordersTotal` can be larger. Empty in demo mode (no order history). */
  orders: CustomerOrder[];
};

/** GET /api/v1/customer?id= */
export async function getCustomerDetail(id: string): Promise<CustomerDetail | null> {
  if (API_MODE === "demo") {
    const customer = mock.customers.find((c) => c.id === id);
    if (!customer) return null;
    return {
      meta: DEMO_META,
      customer,
      firstOrder: null,
      averageOrderValue: customer.orders > 0 ? customer.revenue / customer.orders : null,
      averageDaysBetweenOrders: null,
      ordersTotal: customer.orders,
      orders: [],
    };
  }
  try {
    return await live<CustomerDetail>(`/api/v1/customer?id=${encodeURIComponent(id)}`);
  } catch (error) {
    // Only the backend's own "no such customer" answer; any other 404 (for example an outdated
    // backend without this endpoint) must stay a visible error instead of looking like a missing customer.
    if (error instanceof ApiError && error.code === "customer_not_found") return null;
    throw error;
  }
}

// --- Customers & segments -----------------------------------------------------

export type CustomerList = { meta: DataMeta; total: number; customers: Customer[] };

/** GET /api/v1/customers */
export async function getCustomers(): Promise<CustomerList> {
  if (API_MODE === "demo") {
    return { meta: DEMO_META, total: mock.customers.length, customers: mock.customers };
  }
  return live<CustomerList>("/api/v1/customers");
}

export type SegmentOverview = { meta: DataMeta; segments: SegmentSummary[] };

/** GET /api/v1/segments */
export async function getSegments(): Promise<SegmentOverview> {
  if (API_MODE === "demo") return { meta: DEMO_META, segments: mock.segmentSummary };
  const data = await live<{ meta: DataMeta; segments: SegmentStats[] }>("/api/v1/segments");
  return { meta: data.meta, segments: withSegmentMeta(data.segments) };
}

// --- Churn ---------------------------------------------------------------------

export type ChurnOverview = {
  meta: DataMeta;
  /** null until a churn model exists. */
  churnRate: number | null;
  churnRateDelta: number | null;
  /** Demo: sample churn risk. Live: rule-based inactivity levels. */
  distribution: RiskBucket[];
  customers: Customer[];
};

/** GET /api/v1/predictions/churn */
export async function getChurnOverview(): Promise<ChurnOverview> {
  if (API_MODE === "demo") {
    return {
      meta: DEMO_META,
      churnRate: mock.kpis.churnRisk,
      churnRateDelta: mock.kpiDeltas.churnRisk,
      distribution: mock.riskDistribution,
      customers: [...mock.customers].sort(byChurnDesc),
    };
  }
  return live<ChurnOverview>("/api/v1/predictions/churn");
}

// --- CLV -------------------------------------------------------------------------

export type ClvOverview = {
  meta: DataMeta;
  averageClv: number | null;
  segments: SegmentSummary[];
  customers: Customer[];
};

/** GET /api/v1/predictions/clv */
export async function getClvOverview(): Promise<ClvOverview> {
  if (API_MODE === "demo") {
    const total = mock.segmentSummary.reduce((sum, s) => sum + s.customers, 0);
    return {
      meta: DEMO_META,
      averageClv: mock.segmentSummary.reduce((sum, s) => sum + s.avgClv * s.customers, 0) / total,
      segments: mock.segmentSummary,
      customers: mock.customers,
    };
  }
  const data = await live<Omit<ClvOverview, "segments"> & { segments: SegmentStats[] }>(
    "/api/v1/predictions/clv",
  );
  return { ...data, segments: withSegmentMeta(data.segments) };
}

// --- Revenue ---------------------------------------------------------------------

export type RevenueOverview = {
  meta: DataMeta;
  series: RevenuePoint[];
  /** Demo only: sample monthly revenue-at-risk trend. */
  atRiskTrend: RevenueAtRiskPoint[] | null;
  atRiskBySegment: { segment: SegmentName; atRisk: number; customers: number }[];
  drivers: RevenueDriverGroup[];
};

type RevenueResponse = {
  meta: DataMeta;
  series: RevenuePoint[];
  atRiskBySegment: RevenueOverview["atRiskBySegment"];
  drivers: {
    byCategory: ShareRow[];
    byCountry: ShareRow[];
    newVsReturning: ShareRow[];
  };
};

/** GET /api/v1/revenue/intelligence */
export async function getRevenueOverview(): Promise<RevenueOverview> {
  if (API_MODE === "demo") {
    return {
      meta: DEMO_META,
      series: mock.revenueSeries,
      atRiskTrend: mock.revenueAtRisk,
      atRiskBySegment: mock.revenueAtRiskBySegment,
      drivers: [{ title: "Revenue drivers (sample)", rows: mock.revenueDrivers }],
    };
  }
  const data = await live<RevenueResponse>("/api/v1/revenue/intelligence");
  return {
    meta: data.meta,
    series: data.series,
    atRiskTrend: null,
    atRiskBySegment: data.atRiskBySegment,
    drivers: [
      { title: "By product category (last 12 months)", rows: data.drivers.byCategory },
      { title: "By country (last 12 months)", rows: data.drivers.byCountry },
      { title: "New vs returning customers (last 90 days)", rows: data.drivers.newVsReturning },
    ],
  };
}

// --- Recommendations ---------------------------------------------------------------

export type RecommendationList = { meta: DataMeta; items: Recommendation[] };

/** GET /api/v1/recommendations */
export async function getRecommendations(): Promise<RecommendationList> {
  if (API_MODE === "demo") return { meta: DEMO_META, items: mock.recommendations };
  return live<RecommendationList>("/api/v1/recommendations");
}

// --- Order Risk ----------------------------------------------------------------------------

const DEMO_ORDER_RISK: OrderRiskOverview = {
  meta: DEMO_META,
  model: {
    status: "unavailable", reason: "Demo mode has no order history.", metric: "ROC-AUC",
    modelScore: null, baselineScore: null, modelPrecisionTop: null, baselinePrecisionTop: null,
    topFraction: 0.1, splitDate: null, trainEnd: null, asOf: null, maturityDays: 90, trainRows: 0,
    testRows: 0, testReturnRate: null, labelSource: null, lowBelow: 0.2, highAbove: 0.5,
  },
  windowDays: 30, windowStart: null, windowOrders: 0, levelCounts: { Low: 0, Medium: 0, High: 0 },
  orders: [], truncated: false, savingsHigh: null, savingsMediumHigh: null,
};

/** GET /api/v1/order-risk (live data only: there is no sample order history, so nothing is invented) */
export async function getOrderRisk(limit = 300): Promise<OrderRiskOverview> {
  if (API_MODE === "demo") return DEMO_ORDER_RISK;
  return live<OrderRiskOverview>(`/api/v1/order-risk?limit=${limit}`);
}
