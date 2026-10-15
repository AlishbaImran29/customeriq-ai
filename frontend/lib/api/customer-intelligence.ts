// Customer intelligence service layer (server-only: used by Server Components).
//
// Demo mode (no NEXT_PUBLIC_API_BASE_URL): returns clearly labelled sample data
// from `lib/mock`. Live mode: calls the FastAPI endpoints and maps the response.
// A failed live request throws ApiError — it never falls back to sample data.

import "server-only";
import { connection } from "next/server";
import { API_MODE, apiGet } from "@/lib/api/config";
import * as mock from "@/lib/mock/customer-intelligence";
import { withSegmentMeta } from "@/lib/segments";
import type {
  Customer,
  DataMeta,
  ExecutiveSummary,
  HealthBucket,
  HealthFactors,
  Kpis,
  ModelInfo,
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
  models: { churn: DEMO_MODEL, clv: DEMO_MODEL, forecast: DEMO_MODEL },
  unavailable: [],
};

/** Live requests must run per request, never at build time. */
async function live<T>(path: string): Promise<T> {
  await connection();
  return apiGet<T>(path, { cache: "no-store" });
}

const byChurnDesc = (a: Customer, b: Customer) =>
  (b.churnProbability ?? 0) - (a.churnProbability ?? 0);

// --- Overview -------------------------------------------------------------

export type Overview = {
  meta: DataMeta;
  kpis: Kpis;
  kpiDeltas: Kpis;
  executiveSummary: ExecutiveSummary;
  revenueSeries: RevenuePoint[];
  segments: SegmentSummary[];
  topRecommendations: Recommendation[];
  atRiskCustomers: Customer[];
};

type OverviewResponse = Omit<Overview, "segments"> & { segments: SegmentStats[] };

/** GET /api/v1/dashboard/overview */
export async function getOverview(): Promise<Overview> {
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
    };
  }
  const data = await live<OverviewResponse>("/api/v1/dashboard/overview");
  return { ...data, segments: withSegmentMeta(data.segments) };
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
  /** null until a CLV model exists. */
  averagePredictedClv: number | null;
  segments: SegmentSummary[];
  customers: Customer[];
};

/** GET /api/v1/predictions/clv */
export async function getClvOverview(): Promise<ClvOverview> {
  if (API_MODE === "demo") {
    const total = mock.segmentSummary.reduce((sum, s) => sum + s.customers, 0);
    const weighted = (key: "avgClv" | "avgPredictedClv") =>
      mock.segmentSummary.reduce((sum, s) => sum + (s[key] ?? 0) * s.customers, 0) / total;
    return {
      meta: DEMO_META,
      averageClv: weighted("avgClv"),
      averagePredictedClv: weighted("avgPredictedClv"),
      segments: mock.segmentSummary,
      customers: mock.customers,
    };
  }
  const data = await live<Omit<ClvOverview, "segments"> & { segments: SegmentStats[] }>(
    "/api/v1/predictions/clv",
  );
  return { ...data, segments: withSegmentMeta(data.segments) };
}

// --- Health ----------------------------------------------------------------------

export type HealthWeights = Record<keyof HealthFactors, number>;

export type HealthOverview = {
  meta: DataMeta;
  weights: HealthWeights;
  /** Used for customers without engagement data (engagement left out, not zero). */
  weightsWithoutEngagement: HealthWeights | null;
  distribution: HealthBucket[];
  customers: Customer[];
};

/** GET /api/v1/customers/health */
export async function getHealthOverview(): Promise<HealthOverview> {
  if (API_MODE === "demo") {
    return {
      meta: DEMO_META,
      weights: mock.healthWeights,
      weightsWithoutEngagement: null,
      distribution: mock.healthBreakdown,
      customers: [...mock.customers].sort((a, b) => a.healthScore - b.healthScore),
    };
  }
  return live<HealthOverview>("/api/v1/customers/health");
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
    byChannel: ShareRow[];
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
      { title: "By channel (last 12 months)", rows: data.drivers.byChannel },
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
