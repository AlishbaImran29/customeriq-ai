// MOCK DATA — realistic sample figures used while the FastAPI / ML backend is
// not connected. Only `lib/api/*` should import from this module; UI code reads
// data through the API service layer so this file can be removed later.

import type {
  Customer,
  ExecutiveSummary,
  Kpis,
  Recommendation,
  RevenueAtRiskPoint,
  RevenuePoint,
  RiskBucket,
  RiskLevel,
  SegmentName,
  SegmentSummary,
  ShareRow,
} from "@/lib/types";
import { SEGMENT_META } from "@/lib/segments";

function riskLevelFrom(probability: number): RiskLevel {
  if (probability >= 80) return "Critical";
  if (probability >= 50) return "High";
  if (probability >= 25) return "Medium";
  return "Low";
}

type CustomerSeed = Omit<Customer, "riskLevel">;

const customerSeeds: CustomerSeed[] = [
  {
    id: "CUS-1042", name: "Amelia Chen", email: "amelia.chen@example.com", channel: "Shopify",
    segment: "Champions", orders: 28, revenue: 6420, currentClv: 1840,
    churnProbability: 8, lastPurchase: "2026-10-08",
    recommendedAction: "Invite to VIP early-access drop",
  },
  {
    id: "CUS-1608", name: "Ethan Brooks", email: "ethan.brooks@example.com", channel: "WooCommerce",
    segment: "Champions", orders: 21, revenue: 5120, currentClv: 1610,
    churnProbability: 11, lastPurchase: "2026-10-11",
    recommendedAction: "Upsell annual replenishment plan",
  },
  {
    id: "CUS-1955", name: "Grace Muller", email: "grace.muller@example.com", channel: "Magento",
    segment: "Champions", orders: 24, revenue: 5860, currentClv: 1720,
    churnProbability: 9, lastPurchase: "2026-10-05",
    recommendedAction: "Offer referral rewards for top advocates",
  },
  {
    id: "CUS-1188", name: "Noah Patel", email: "noah.patel@example.com", channel: "WooCommerce",
    segment: "Loyal Customers", orders: 16, revenue: 3180, currentClv: 920,
    churnProbability: 18, lastPurchase: "2026-09-29",
    recommendedAction: "Cross-sell complementary bundle",
  },
  {
    id: "CUS-1830", name: "Omar Haddad", email: "omar.haddad@example.com", channel: "Magento",
    segment: "Loyal Customers", orders: 14, revenue: 2740, currentClv: 740,
    churnProbability: 22, lastPurchase: "2026-09-22",
    recommendedAction: "Request referral after next order",
  },
  {
    id: "CUS-2017", name: "Isabella Rossi", email: "isabella.rossi@example.com", channel: "Shopify",
    segment: "Loyal Customers", orders: 12, revenue: 2310, currentClv: 680,
    churnProbability: 27, lastPurchase: "2026-09-14",
    recommendedAction: "Introduce loyalty tier upgrade",
  },
  {
    id: "CUS-1411", name: "Liam Okafor", email: "liam.okafor@example.com", channel: "Magento",
    segment: "Potential Loyalists", orders: 5, revenue: 890, currentClv: 240,
    churnProbability: 34, lastPurchase: "2026-09-18",
    recommendedAction: "Nurture with second-purchase incentive",
  },
  {
    id: "CUS-2104", name: "Chloe Martin", email: "chloe.martin@example.com", channel: "Shopify",
    segment: "Potential Loyalists", orders: 4, revenue: 640, currentClv: 210,
    churnProbability: 29, lastPurchase: "2026-10-02",
    recommendedAction: "Recommend products from browsing history",
  },
  {
    id: "CUS-2231", name: "Daniel Nguyen", email: "daniel.nguyen@example.com", channel: "WooCommerce",
    segment: "Potential Loyalists", orders: 3, revenue: 470, currentClv: 180,
    churnProbability: 41, lastPurchase: "2026-08-27",
    recommendedAction: "Day-30 nurture journey with free shipping",
  },
  {
    id: "CUS-1304", name: "Sofia Alvarez", email: "sofia.alvarez@example.com", channel: "Shopify",
    segment: "At-Risk Customers", orders: 9, revenue: 1470, currentClv: 410,
    churnProbability: 72, lastPurchase: "2026-06-12",
    recommendedAction: "Launch 20% win-back campaign",
  },
  {
    id: "CUS-1722", name: "Hana Kim", email: "hana.kim@example.com", channel: "Shopify",
    segment: "At-Risk Customers", orders: 7, revenue: 980, currentClv: 265,
    churnProbability: 64, lastPurchase: "2026-07-01",
    recommendedAction: "Re-engagement email with loyalty points",
  },
  {
    id: "CUS-2368", name: "Lucas Silva", email: "lucas.silva@example.com", channel: "WooCommerce",
    segment: "At-Risk Customers", orders: 11, revenue: 1890, currentClv: 520,
    churnProbability: 58, lastPurchase: "2026-07-19",
    recommendedAction: "Personal outreach from customer success",
  },
  {
    id: "CUS-1520", name: "Maya Singh", email: "maya.singh@example.com", channel: "Shopify",
    segment: "Lost Customers", orders: 3, revenue: 210, currentClv: 88,
    churnProbability: 91, lastPurchase: "2026-02-03",
    recommendedAction: "Recovery survey + exclusive restart offer",
  },
  {
    id: "CUS-2479", name: "Jonas Berg", email: "jonas.berg@example.com", channel: "Magento",
    segment: "Lost Customers", orders: 2, revenue: 160, currentClv: 64,
    churnProbability: 87, lastPurchase: "2026-01-21",
    recommendedAction: "Sunset to low-frequency newsletter",
  },
];

export const customers: Customer[] = customerSeeds.map((seed) => ({
  ...seed,
  riskLevel: riskLevelFrom(seed.churnProbability ?? 0),
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
    name: "Champions", customers: 2140, revenue: 892400, avgClv: 1248,
    ...SEGMENT_META["Champions"],
  },
  {
    name: "Loyal Customers", customers: 4860, revenue: 764200, avgClv: 542,
    ...SEGMENT_META["Loyal Customers"],
  },
  {
    name: "Potential Loyalists", customers: 5210, revenue: 498650, avgClv: 286,
    ...SEGMENT_META["Potential Loyalists"],
  },
  {
    name: "At-Risk Customers", customers: 3680, revenue: 246800, avgClv: 198,
    ...SEGMENT_META["At-Risk Customers"],
  },
  {
    name: "Lost Customers", customers: 2530, revenue: 85600, avgClv: 74,
    ...SEGMENT_META["Lost Customers"],
  },
];

// Sample monthly revenue (October is the last month).
export const revenueSeries: RevenuePoint[] = [
  { month: "Apr", actual: 168400 },
  { month: "May", actual: 182200 },
  { month: "Jun", actual: 176800 },
  { month: "Jul", actual: 194500 },
  { month: "Aug", actual: 201300 },
  { month: "Sep", actual: 188900 },
  { month: "Oct", actual: 216400 },
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

export const revenueDrivers: ShareRow[] = [
  { name: "Repeat Champion orders", revenue: 312000, share: 28 },
  { name: "Loyal customer replenishment", revenue: 246000, share: 22 },
  { name: "New Potential Loyalist conversions", revenue: 188000, share: 17 },
  { name: "Seasonal campaign revenue", revenue: 154000, share: 14 },
  { name: "Upsell / cross-sell", revenue: 121000, share: 11 },
  { name: "Recovered at-risk customers", revenue: 89000, share: 8 },
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
    detail: "Champions generate 36% of revenue. Subscription or 90-day refill plans can lift lifetime value by ~18%.",
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
    detail: "Lost Customers still represent Rs. 85.6k historical revenue. A one-time restart offer plus survey can identify product-fit issues.",
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
    "Champions keep growing their lifetime value; At-Risk and Lost cohorts are shrinking.",
    "Highest-leverage next action: recover At-Risk customers before peak season demand.",
  ],
};

export const riskDistribution: RiskBucket[] = [
  { level: "Low", customers: 9840 },
  { level: "Medium", customers: 5970 },
  { level: "High", customers: 1760 },
  { level: "Critical", customers: 850 },
];
