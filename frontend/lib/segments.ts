import type { SegmentName, SegmentStats, SegmentSummary } from "@/lib/types";

export const SEGMENT_ORDER: SegmentName[] = [
  "Champions",
  "Loyal Customers",
  "Potential Loyalists",
  "At-Risk Customers",
  "Lost Customers",
];

// Colours follow the validated categorical order (fixed per segment, never by rank).
// Definitions describe the RFM rules used by the backend (app/services/analytics.py).
export const SEGMENT_META: Record<
  SegmentName,
  { color: string; definition: string; strategy: string }
> = {
  Champions: {
    color: "#22d3ee",
    definition: "Bought recently, buy often, and spend the most.",
    strategy: "Reward, request reviews and referrals, offer early access.",
  },
  "Loyal Customers": {
    color: "#a78bfa",
    definition: "Buy regularly with above-average frequency and spend.",
    strategy: "Upsell higher-value products and loyalty tiers.",
  },
  "Potential Loyalists": {
    color: "#34d399",
    definition: "Recent customers who have not ordered often yet.",
    strategy: "Nurture toward repeat purchase with timed incentives.",
  },
  "At-Risk Customers": {
    color: "#fbbf24",
    definition: "Used to buy often or spend a lot, but not recently.",
    strategy: "Personalised win-back offers before they lapse.",
  },
  "Lost Customers": {
    color: "#f472b6",
    definition: "Lowest recency, frequency, and spend.",
    strategy: "Low-cost recovery offer and feedback survey.",
  },
};

export function withSegmentMeta(stats: SegmentStats[]): SegmentSummary[] {
  return stats.map((s) => ({ ...s, ...SEGMENT_META[s.name] }));
}
