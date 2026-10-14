// MOCK DATA — realistic sample figures used while the FastAPI / ML backend is
// not connected. Only `lib/api/*` should import from this module; UI code reads
// data through the API service layer so this file can be removed later.

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
  RiskLevel,
  SegmentName,
  SegmentSummary,
} from "@/lib/types";

/** Weights used by the sample health score (mirrors the planned backend formula). */
export const healthWeights: Record<keyof HealthFactors, number> = {
  purchaseFrequency: 0.3,
  spendingBehavior: 0.3,
  engagement: 0.2,
  activityTrend: 0.2,
};

function healthScoreFrom(factors: HealthFactors) {
  return Math.round(
    (Object.keys(healthWeights) as (keyof HealthFactors)[]).reduce(
      (total, key) => total + factors[key] * healthWeights[key],
      0,
    ),
  );
}

function riskLevelFrom(probability: number): RiskLevel {
  if (probability >= 80) return "Critical";
  if (probability >= 50) return "High";
  if (probability >= 25) return "Medium";
  return "Low";
}

type CustomerSeed = Omit<Customer, "riskLevel" | "healthScore">;

const customerSeeds: CustomerSeed[] = [
  {
    id: "CUS-1042", name: "Amelia Chen", email: "amelia.chen@example.com", store: "Shopify",
    segment: "Champions", orders: 28, revenue: 6420, currentClv: 1840, predictedClv: 2460,
    churnProbability: 8, lastPurchase: "2026-10-08",
    healthFactors: { purchaseFrequency: 96, spendingBehavior: 94, engagement: 91, activityTrend: 92 },
    recommendedAction: "Invite to VIP early-access drop",
  },
  {
    id: "CUS-1608", name: "Ethan Brooks", email: "ethan.brooks@example.com", store: "WooCommerce",
    segment: "Champions", orders: 21, revenue: 5120, currentClv: 1610, predictedClv: 1980,
    churnProbability: 11, lastPurchase: "2026-10-11",
    healthFactors: { purchaseFrequency: 90, spendingBehavior: 92, engagement: 84, activityTrend: 88 },
    recommendedAction: "Upsell annual replenishment plan",
  },
  {
    id: "CUS-1955", name: "Grace Muller", email: "grace.muller@example.com", store: "Magento",
    segment: "Champions", orders: 24, revenue: 5860, currentClv: 1720, predictedClv: 2140,
    churnProbability: 9, lastPurchase: "2026-10-05",
    healthFactors: { purchaseFrequency: 93, spendingBehavior: 95, engagement: 79, activityTrend: 86 },
    recommendedAction: "Offer referral rewards for top advocates",
  },
  {
    id: "CUS-1188", name: "Noah Patel", email: "noah.patel@example.com", store: "WooCommerce",
    segment: "Loyal Customers", orders: 16, revenue: 3180, currentClv: 920, predictedClv: 1280,
    churnProbability: 18, lastPurchase: "2026-09-29",
    healthFactors: { purchaseFrequency: 84, spendingBehavior: 78, engagement: 80, activityTrend: 82 },
    recommendedAction: "Cross-sell complementary bundle",
  },
  {
    id: "CUS-1830", name: "Omar Haddad", email: "omar.haddad@example.com", store: "Magento",
    segment: "Loyal Customers", orders: 14, revenue: 2740, currentClv: 740, predictedClv: 910,
    churnProbability: 22, lastPurchase: "2026-09-22",
    healthFactors: { purchaseFrequency: 80, spendingBehavior: 72, engagement: 76, activityTrend: 74 },
    recommendedAction: "Request referral after next order",
  },
  {
    id: "CUS-2017", name: "Isabella Rossi", email: "isabella.rossi@example.com", store: "Shopify",
    segment: "Loyal Customers", orders: 12, revenue: 2310, currentClv: 680, predictedClv: 820,
    churnProbability: 27, lastPurchase: "2026-09-14",
    healthFactors: { purchaseFrequency: 74, spendingBehavior: 70, engagement: 66, activityTrend: 62 },
    recommendedAction: "Introduce loyalty tier upgrade",
  },
  {
    id: "CUS-1411", name: "Liam Okafor", email: "liam.okafor@example.com", store: "Magento",
    segment: "Potential Loyalists", orders: 5, revenue: 890, currentClv: 240, predictedClv: 610,
    churnProbability: 34, lastPurchase: "2026-09-18",
    healthFactors: { purchaseFrequency: 58, spendingBehavior: 60, engagement: 72, activityTrend: 70 },
    recommendedAction: "Nurture with second-purchase incentive",
  },
  {
    id: "CUS-2104", name: "Chloe Martin", email: "chloe.martin@example.com", store: "Shopify",
    segment: "Potential Loyalists", orders: 4, revenue: 640, currentClv: 210, predictedClv: 540,
    churnProbability: 29, lastPurchase: "2026-10-02",
    healthFactors: { purchaseFrequency: 55, spendingBehavior: 52, engagement: 78, activityTrend: 76 },
    recommendedAction: "Recommend products from browsing history",
  },
  {
    id: "CUS-2231", name: "Daniel Nguyen", email: "daniel.nguyen@example.com", store: "WooCommerce",
    segment: "Potential Loyalists", orders: 3, revenue: 470, currentClv: 180, predictedClv: 420,
    churnProbability: 41, lastPurchase: "2026-08-27",
    healthFactors: { purchaseFrequency: 46, spendingBehavior: 50, engagement: 61, activityTrend: 58 },
    recommendedAction: "Day-30 nurture journey with free shipping",
  },
  {
    id: "CUS-1304", name: "Sofia Alvarez", email: "sofia.alvarez@example.com", store: "Shopify",
    segment: "At-Risk Customers", orders: 9, revenue: 1470, currentClv: 410, predictedClv: 290,
    churnProbability: 72, lastPurchase: "2026-06-12",
    healthFactors: { purchaseFrequency: 42, spendingBehavior: 48, engagement: 30, activityTrend: 24 },
    recommendedAction: "Launch 20% win-back campaign",
  },
  {
    id: "CUS-1722", name: "Hana Kim", email: "hana.kim@example.com", store: "Shopify",
    segment: "At-Risk Customers", orders: 7, revenue: 980, currentClv: 265, predictedClv: 180,
    churnProbability: 64, lastPurchase: "2026-07-01",
    healthFactors: { purchaseFrequency: 45, spendingBehavior: 44, engagement: 38, activityTrend: 36 },
    recommendedAction: "Re-engagement email with loyalty points",
  },
  {
    id: "CUS-2368", name: "Lucas Silva", email: "lucas.silva@example.com", store: "WooCommerce",
    segment: "At-Risk Customers", orders: 11, revenue: 1890, currentClv: 520, predictedClv: 340,
    churnProbability: 58, lastPurchase: "2026-07-19",
    healthFactors: { purchaseFrequency: 52, spendingBehavior: 58, engagement: 34, activityTrend: 30 },
    recommendedAction: "Personal outreach from customer success",
  },
  {
    id: "CUS-1520", name: "Maya Singh", email: "maya.singh@example.com", store: "Shopify",
    segment: "Lost Customers", orders: 3, revenue: 210, currentClv: 88, predictedClv: 40,
    churnProbability: 91, lastPurchase: "2026-02-03",
    healthFactors: { purchaseFrequency: 18, spendingBehavior: 20, engagement: 12, activityTrend: 8 },
    recommendedAction: "Recovery survey + exclusive restart offer",
  },
  {
    id: "CUS-2479", name: "Jonas Berg", email: "jonas.berg@example.com", store: "Magento",
    segment: "Lost Customers", orders: 2, revenue: 160, currentClv: 64, predictedClv: 25,
    churnProbability: 87, lastPurchase: "2026-01-21",
    healthFactors: { purchaseFrequency: 14, spendingBehavior: 18, engagement: 16, activityTrend: 10 },
    recommendedAction: "Sunset to low-frequency newsletter",
  },
];

export const customers: Customer[] = customerSeeds.map((seed) => ({
  ...seed,
  riskLevel: riskLevelFrom(seed.churnProbability),
  healthScore: healthScoreFrom(seed.healthFactors),
}));

export const kpis: Kpis = {
  totalCustomers: 18420,
  revenue: 2487650,
  averageClv: 412,
  retentionRate: 68.4,
  churnRisk: 14.2,
  growthScore: 78,
};

export const kpiDeltas: Kpis = {
  totalCustomers: 4.8,
  revenue: 6.1,
  averageClv: 3.2,
  retentionRate: -1.4,
  churnRisk: 2.1,
  growthScore: 5.0,
};

// Colors follow the validated categorical order (fixed per segment, never by rank).
export const segmentSummary: SegmentSummary[] = [
  {
    name: "Champions", customers: 2140, revenue: 892400, avgClv: 1248, avgPredictedClv: 1512,
    color: "#2a78d6",
    definition: "Bought recently, buy often, and spend the most.",
    strategy: "Reward, request reviews and referrals, offer early access.",
  },
  {
    name: "Loyal Customers", customers: 4860, revenue: 764200, avgClv: 542, avgPredictedClv: 668,
    color: "#eb6834",
    definition: "Purchase regularly and respond well to promotions.",
    strategy: "Upsell higher-value products and loyalty tiers.",
  },
  {
    name: "Potential Loyalists", customers: 5210, revenue: 498650, avgClv: 286, avgPredictedClv: 431,
    color: "#1baf7a",
    definition: "Recent customers with above-average spend and 2–5 orders.",
    strategy: "Nurture toward repeat purchase with timed incentives.",
  },
  {
    name: "At-Risk Customers", customers: 3680, revenue: 246800, avgClv: 198, avgPredictedClv: 142,
    color: "#eda100",
    definition: "Previously active, but no purchase in 60+ days.",
    strategy: "Personalised win-back offers before they lapse.",
  },
  {
    name: "Lost Customers", customers: 2530, revenue: 85600, avgClv: 74, avgPredictedClv: 31,
    color: "#e87ba4",
    definition: "Lowest recency, frequency, and spend; inactive 180+ days.",
    strategy: "Low-cost recovery offer and feedback survey.",
  },
];

// "Oct" is the last actual month; Nov–Jan are forecast with a confidence band.
export const revenueSeries: RevenuePoint[] = [
  { month: "Apr", actual: 168400 },
  { month: "May", actual: 182200 },
  { month: "Jun", actual: 176800 },
  { month: "Jul", actual: 194500 },
  { month: "Aug", actual: 201300 },
  { month: "Sep", actual: 188900 },
  { month: "Oct", actual: 216400, forecast: 216400, range: [216400, 216400] },
  { month: "Nov", forecast: 231800, range: [219500, 244100] },
  { month: "Dec", forecast: 258300, range: [239600, 277000] },
  { month: "Jan", forecast: 209700, range: [187900, 231500] },
];

export const revenueAtRisk: RevenueAtRiskPoint[] = [
  { month: "Apr", atRisk: 18400 },
  { month: "May", atRisk: 21100 },
  { month: "Jun", atRisk: 24600 },
  { month: "Jul", atRisk: 22800 },
  { month: "Aug", atRisk: 27400 },
  { month: "Sep", atRisk: 31200 },
  { month: "Oct", atRisk: 29800 },
];

export const revenueAtRiskBySegment: { segment: SegmentName; atRisk: number; customers: number }[] = [
  { segment: "At-Risk Customers", atRisk: 94200, customers: 3680 },
  { segment: "Lost Customers", atRisk: 41300, customers: 2530 },
  { segment: "Potential Loyalists", atRisk: 28700, customers: 5210 },
  { segment: "Loyal Customers", atRisk: 16900, customers: 4860 },
];

export const revenueDrivers: RevenueDriver[] = [
  { driver: "Repeat Champion orders", impact: 312000, share: 28 },
  { driver: "Loyal customer replenishment", impact: 246000, share: 22 },
  { driver: "New Potential Loyalist conversions", impact: 188000, share: 17 },
  { driver: "Seasonal campaign revenue", impact: 154000, share: 14 },
  { driver: "Upsell / cross-sell", impact: 121000, share: 11 },
  { driver: "Recovered at-risk customers", impact: 89000, share: 8 },
];

export const recommendations: Recommendation[] = [
  {
    id: "REC-01", category: "Retention Campaign",
    title: "Win back the At-Risk cohort before Q4 peak",
    detail: "3,680 at-risk customers have not purchased in 60+ days. A 15–20% personalised offer can recover a large share of the revenue at risk.",
    impact: "High", targetSegment: "At-Risk Customers", audienceSize: 3680, estimatedRevenue: 94000,
    nextAction: "Launch segmented email + SMS sequence this week",
  },
  {
    id: "REC-02", category: "Retention Campaign",
    title: "Nurture Potential Loyalists into Loyal Customers",
    detail: "5,210 Potential Loyalists are one successful second or third purchase away from loyalty. A timed incentive raises conversion odds.",
    impact: "High", targetSegment: "Potential Loyalists", audienceSize: 5210, estimatedRevenue: 72000,
    nextAction: "Trigger day-14 and day-30 nurture journeys",
  },
  {
    id: "REC-03", category: "Upsell",
    title: "Offer replenishment plans to Champions",
    detail: "Champions generate 36% of revenue. Subscription or 90-day refill plans can lift predicted CLV by ~18%.",
    impact: "High", targetSegment: "Champions", audienceSize: 2140, estimatedRevenue: 118000,
    nextAction: "Enable checkout upsell for top 500 SKUs",
  },
  {
    id: "REC-04", category: "Upsell",
    title: "Promote premium tier to high-AOV Loyal Customers",
    detail: "Loyal Customers in the top AOV quartile buy premium variants 2.3x more often when shown side-by-side comparisons.",
    impact: "Medium", targetSegment: "Loyal Customers", audienceSize: 1215, estimatedRevenue: 38000,
    nextAction: "Add premium comparison block to post-purchase email",
  },
  {
    id: "REC-05", category: "Cross-Sell",
    title: "Bundle complementary products for Loyal Customers",
    detail: "Loyal Customers average 16 orders but have a low attach rate. Bundles can increase AOV without increasing churn risk.",
    impact: "Medium", targetSegment: "Loyal Customers", audienceSize: 4860, estimatedRevenue: 54000,
    nextAction: "Create 3 bundles from frequently co-purchased items",
  },
  {
    id: "REC-06", category: "Cross-Sell",
    title: "Recommend accessories after first purchase",
    detail: "Potential Loyalists who add an accessory within 30 days are far more likely to place a third order.",
    impact: "Low", targetSegment: "Potential Loyalists", audienceSize: 5210, estimatedRevenue: 21000,
    nextAction: "Add accessory carousel to order-shipped email",
  },
  {
    id: "REC-07", category: "Customer Recovery",
    title: "Recover Lost Customers with a restart offer",
    detail: "Lost Customers still represent $85.6k historical revenue. A one-time restart offer plus survey can identify product-fit issues.",
    impact: "Medium", targetSegment: "Lost Customers", audienceSize: 2530, estimatedRevenue: 26000,
    nextAction: "Send recovery campaign with 30-day expiry",
  },
  {
    id: "REC-08", category: "Customer Recovery",
    title: "Survey lapsed customers on why they left",
    detail: "Understanding the top three churn reasons improves targeting for every future win-back campaign.",
    impact: "Low", targetSegment: "Lost Customers", audienceSize: 2530, estimatedRevenue: 9000,
    nextAction: "Send a 3-question survey with a small thank-you credit",
  },
];

export const executiveSummary: ExecutiveSummary = {
  headline: "Revenue is growing, but retention pressure is rising.",
  bullets: [
    "October revenue is up 14.6% on September, led by Champions and Loyal Customers.",
    "Churn risk increased 2.1 pts, driven by At-Risk Customers inactive since mid-summer.",
    "Predicted CLV is still expanding for Champions; At-Risk and Lost cohorts are contracting.",
    "Highest-leverage next action: recover At-Risk customers before peak season demand.",
  ],
};

export const healthBreakdown: HealthBucket[] = [
  { range: "90–100", label: "Excellent", customers: 1980 },
  { range: "75–89", label: "Healthy", customers: 5240 },
  { range: "55–74", label: "Watch", customers: 6120 },
  { range: "30–54", label: "At risk", customers: 3210 },
  { range: "0–29", label: "Critical", customers: 1870 },
];

export const riskDistribution: RiskBucket[] = [
  { level: "Low", customers: 9840 },
  { level: "Medium", customers: 5970 },
  { level: "High", customers: 1760 },
  { level: "Critical", customers: 850 },
];

export const assistantReplies: { match: string[]; answer: string }[] = [
  {
    match: ["churn", "likely", "leave", "stop"],
    answer:
      "Highest churn likelihood is in the At-Risk and Lost segments. Examples: Maya Singh (91%), Jonas Berg (87%), and Sofia Alvarez (72%). Recommended actions are a 20% win-back campaign for At-Risk customers and a recovery offer plus survey for Lost customers.",
  },
  {
    match: ["revenue decrease", "decrease", "drop", "why did revenue"],
    answer:
      "September dipped versus August because repeat purchase frequency slowed among At-Risk Customers and revenue at risk rose to $31.2k. October recovered to $216.4k, led by Champion repeat orders.",
  },
  {
    match: ["segment", "profit", "highest revenue", "most valuable"],
    answer:
      "Champions generate the highest revenue ($892k) and the highest average CLV ($1,248). Loyal Customers are second at $764k. Profit margins are not part of the sample data, so this answer uses revenue.",
  },
  {
    match: ["clv", "lifetime"],
    answer:
      "Average CLV is $412. Champions show the strongest growth potential (avg $1,248 to $1,512 predicted). At-Risk and Lost customers have declining predicted CLV, which is a retention warning.",
  },
  {
    match: ["retention", "retain", "loyal"],
    answer:
      "Retention is 68.4% (down 1.4 pts). The two highest-impact retention plays are the At-Risk win-back campaign (~$94k potential) and nurturing 5,210 Potential Loyalists into Loyal Customers.",
  },
  {
    match: ["health", "score"],
    answer:
      "Health scores weight purchase frequency (30%), spending (30%), engagement (20%), and activity trend (20%). 5,080 customers are in the At risk or Critical bands, mostly from the At-Risk and Lost segments.",
  },
  {
    match: ["upsell", "cross", "recommend", "grow"],
    answer:
      "Top growth opportunities: replenishment plans for Champions (~$118k), the At-Risk win-back (~$94k), and nurture journeys for Potential Loyalists (~$72k). See the Recommendations page for all actions.",
  },
];