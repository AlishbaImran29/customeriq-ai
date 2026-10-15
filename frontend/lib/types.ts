// Domain types shared by the UI, the mock data module, and the API service layer.
// They mirror the FastAPI response shapes (backend/app/schemas/analytics.py).
//
// `null` means "not available": predictions (churn probability, predicted CLV,
// forecasts) are only present when their model passed a quality gate (see
// `DataMeta.models`); the growth score stays null (no agreed formula).

export type SegmentName =
  | "Champions"
  | "Loyal Customers"
  | "Potential Loyalists"
  | "At-Risk Customers"
  | "Lost Customers";

export type RiskLevel = "Low" | "Medium" | "High" | "Critical";

export type DataSource = "demo" | "live";

/** Whether a prediction model is available, and how it did on unseen data. */
export type ModelInfo = {
  status: "available" | "unavailable";
  /** Why it is unavailable (not enough data, or not better than a simple rule). */
  reason: string | null;
  /** Validation results: tested on a later period the model was not trained on. */
  metrics: { label: string; value: string }[];
};

export type ModelsMeta = { churn: ModelInfo; clv: ModelInfo; forecast: ModelInfo };

/** Context returned with every analytics response. */
export type DataMeta = {
  source: DataSource;
  /** Latest order date in the data; null when nothing has been imported. */
  asOf: string | null;
  customerCount: number;
  /** False when there are too few customers to segment. */
  segmented: boolean;
  models: ModelsMeta;
  /** Values that cannot be shown yet, with the reason. */
  unavailable: { field: string; reason: string }[];
};

/** Inputs to the customer health score, each 0–100. */
export type HealthFactors = {
  purchaseFrequency: number;
  spendingBehavior: number;
  /** null = no engagement data; the score re-weights the other factors. */
  engagement: number | null;
  activityTrend: number;
};

export type Customer = {
  id: string;
  name: string;
  email: string;
  /** Sales channel or store platform, e.g. "Shopify". */
  channel: string | null;
  /** null when there are too few customers to segment. */
  segment: SegmentName | null;
  orders: number;
  revenue: number;
  /** Revenue to date (historical CLV). */
  currentClv: number;
  predictedClv: number | null;
  /** 0–100; null unless the churn model passed its quality gate. */
  churnProbability: number | null;
  /**
   * Demo data: sample churn risk. Live data: from the churn probability when a
   * churn model is available, otherwise the rule-based inactivity level
   * (days since last order ÷ usual gap between orders) — not a prediction.
   */
  riskLevel: RiskLevel;
  /** 0–100, weighted from `healthFactors`. */
  healthScore: number;
  healthFactors: HealthFactors;
  engagementMissing?: boolean;
  lastPurchase: string;
  daysSinceLastOrder?: number;
  recommendedAction: string;
};

export type Kpis = {
  totalCustomers: number | null;
  revenue: number | null;
  averageClv: number | null;
  retentionRate: number | null;
  churnRisk: number | null;
  growthScore: number | null;
};

/** How the Growth Score was calculated: our own composite of measured metrics. */
export type GrowthScoreDetails = {
  score: number;
  components: { key: string; label: string; measure: string; value: number; weight: number }[];
  /** Inputs left out because there is not enough history yet. */
  missing: string[];
};

export type SegmentStats = {
  name: SegmentName;
  customers: number;
  revenue: number;
  avgClv: number;
  avgPredictedClv: number | null;
};

/** Segment numbers plus the UI's fixed colour and wording. */
export type SegmentSummary = SegmentStats & {
  color: string;
  definition: string;
  strategy: string;
};

export type RevenuePoint = {
  month: string;
  /** Recorded revenue; absent for forecast-only months. */
  actual?: number;
  /** Model forecast; absent when no forecast exists. */
  forecast?: number;
  /** Forecast confidence interval [low, high]. */
  range?: [number, number];
  /** True for a month that is not over yet (month to date). */
  partial?: boolean;
};

export type RevenueAtRiskPoint = { month: string; atRisk: number };

export type ShareRow = { name: string; revenue: number; share: number };

export type RevenueDriverGroup = { title: string; rows: ShareRow[] };

export type RecommendationCategory =
  | "Retention Campaign"
  | "Upsell"
  | "Cross-Sell"
  | "Customer Recovery";

export type ImpactLevel = "High" | "Medium" | "Low";

export type Recommendation = {
  id: string;
  category: RecommendationCategory;
  title: string;
  detail: string;
  impact: ImpactLevel;
  targetSegment: SegmentName;
  audienceSize: number;
  /** Sample estimate in demo mode; always null for live data (no model). */
  estimatedRevenue: number | null;
  /** Live data: what this audience actually spent in the last 12 months. */
  historicalRevenue?: number | null;
  nextAction: string;
};

export type HealthBucket = { range: string; label: string; customers: number };

export type RiskBucket = { level: RiskLevel; customers: number };

export type ExecutiveSummary = {
  headline: string;
  bullets: string[];
  /** "rules" = generated from real numbers with fixed rules (no AI). */
  method?: "rules" | "sample";
};
