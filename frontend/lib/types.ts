// Domain types shared by the UI, the mock data module, and the API service layer.
// These mirror the response shapes expected from the FastAPI backend.

export type SegmentName =
  | "Champions"
  | "Loyal Customers"
  | "Potential Loyalists"
  | "At-Risk Customers"
  | "Lost Customers";

export type RiskLevel = "Low" | "Medium" | "High" | "Critical";

export type StoreSource = "Shopify" | "WooCommerce" | "Magento";

/** Inputs to the customer health score, each normalised to 0–100. */
export type HealthFactors = {
  purchaseFrequency: number;
  spendingBehavior: number;
  engagement: number;
  activityTrend: number;
};

export type Customer = {
  id: string;
  name: string;
  email: string;
  store: StoreSource;
  segment: SegmentName;
  orders: number;
  revenue: number;
  currentClv: number;
  predictedClv: number;
  /** 0–100 */
  churnProbability: number;
  riskLevel: RiskLevel;
  /** 0–100, weighted from `healthFactors` */
  healthScore: number;
  healthFactors: HealthFactors;
  lastPurchase: string;
  recommendedAction: string;
};

export type Kpis = {
  totalCustomers: number;
  revenue: number;
  averageClv: number;
  retentionRate: number;
  churnRisk: number;
  growthScore: number;
};

export type SegmentSummary = {
  name: SegmentName;
  customers: number;
  revenue: number;
  avgClv: number;
  avgPredictedClv: number;
  color: string;
  definition: string;
  strategy: string;
};

export type RevenuePoint = {
  month: string;
  /** Recorded revenue; absent for forecast-only months. */
  actual?: number;
  /** Model forecast; absent for months before the forecast window. */
  forecast?: number;
  /** Forecast confidence interval [low, high]. */
  range?: [number, number];
};

export type RevenueAtRiskPoint = { month: string; atRisk: number };

export type RevenueDriver = { driver: string; impact: number; share: number };

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
  estimatedRevenue: number;
  nextAction: string;
};

export type HealthBucket = { range: string; label: string; customers: number };

export type RiskBucket = { level: RiskLevel; customers: number };

export type ExecutiveSummary = { headline: string; bullets: string[] };
