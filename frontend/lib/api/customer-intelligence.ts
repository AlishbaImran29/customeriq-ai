// Customer intelligence service layer.
//
// Pages call these functions instead of importing mock data directly. Each
// function documents the backend endpoint it is intended to call; today they
// resolve with mock data (see DATA_SOURCE in ./config).

import * as mock from "@/lib/mock/customer-intelligence";
import type {
  Customer,
  ExecutiveSummary,
  HealthBucket,
  HealthFactors,
  Kpis,
  Recommendation,
  RevenueAtRiskPoint,
  RevenueDriver,
  RevenuePoint,
  RiskBucket,
  SegmentName,
  SegmentSummary,
} from "@/lib/types";

export type Overview = {
  kpis: Kpis;
  kpiDeltas: Kpis;
  executiveSummary: ExecutiveSummary;
  revenueSeries: RevenuePoint[];
  segments: SegmentSummary[];
  topRecommendations: Recommendation[];
  atRiskCustomers: Customer[];
};

/** Planned endpoint: GET /api/v1/dashboard/overview */
export async function getOverview(): Promise<Overview> {
  return {
    kpis: mock.kpis,
    kpiDeltas: mock.kpiDeltas,
    executiveSummary: mock.executiveSummary,
    revenueSeries: mock.revenueSeries,
    segments: mock.segmentSummary,
    topRecommendations: mock.recommendations
      .filter((item) => item.impact === "High")
      .slice(0, 3),
    atRiskCustomers: [...mock.customers]
      .sort((a, b) => b.churnProbability - a.churnProbability)
      .slice(0, 4),
  };
}

/** Planned endpoint: GET /api/v1/customers */
export async function getCustomers(): Promise<Customer[]> {
  return mock.customers;
}

/** Planned endpoint: GET /api/v1/segments */
export async function getSegments(): Promise<SegmentSummary[]> {
  return mock.segmentSummary;
}

export type ChurnOverview = {
  churnRate: number;
  churnRateDelta: number;
  distribution: RiskBucket[];
  customers: Customer[];
};

/** Planned endpoint: GET /api/v1/predictions/churn */
export async function getChurnOverview(): Promise<ChurnOverview> {
  return {
    churnRate: mock.kpis.churnRisk,
    churnRateDelta: mock.kpiDeltas.churnRisk,
    distribution: mock.riskDistribution,
    customers: [...mock.customers].sort(
      (a, b) => b.churnProbability - a.churnProbability,
    ),
  };
}

export type ClvOverview = {
  averageClv: number;
  averagePredictedClv: number;
  segments: SegmentSummary[];
  customers: Customer[];
};

/** Planned endpoint: GET /api/v1/predictions/clv */
export async function getClvOverview(): Promise<ClvOverview> {
  const total = mock.segmentSummary.reduce((sum, s) => sum + s.customers, 0);
  const weighted = (key: "avgClv" | "avgPredictedClv") =>
    mock.segmentSummary.reduce((sum, s) => sum + s[key] * s.customers, 0) / total;
  return {
    averageClv: weighted("avgClv"),
    averagePredictedClv: weighted("avgPredictedClv"),
    segments: mock.segmentSummary,
    customers: mock.customers,
  };
}

export type HealthOverview = {
  weights: Record<keyof HealthFactors, number>;
  distribution: HealthBucket[];
  customers: Customer[];
};

/** Planned endpoint: GET /api/v1/customers/health */
export async function getHealthOverview(): Promise<HealthOverview> {
  return {
    weights: mock.healthWeights,
    distribution: mock.healthBreakdown,
    customers: [...mock.customers].sort((a, b) => a.healthScore - b.healthScore),
  };
}

export type RevenueOverview = {
  series: RevenuePoint[];
  atRiskTrend: RevenueAtRiskPoint[];
  atRiskBySegment: { segment: SegmentName; atRisk: number; customers: number }[];
  drivers: RevenueDriver[];
};

/** Planned endpoint: GET /api/v1/revenue/intelligence */
export async function getRevenueOverview(): Promise<RevenueOverview> {
  return {
    series: mock.revenueSeries,
    atRiskTrend: mock.revenueAtRisk,
    atRiskBySegment: mock.revenueAtRiskBySegment,
    drivers: mock.revenueDrivers,
  };
}

/** Planned endpoint: GET /api/v1/recommendations */
export async function getRecommendations(): Promise<Recommendation[]> {
  return mock.recommendations;
}