import { DemoBanner } from "@/components/demo-banner";
import { PageHeader } from "@/components/page-header";
import { RecommendationBoard } from "@/components/recommendation-board";
import { Card } from "@/components/ui/card";
import { getRecommendations } from "@/lib/api/customer-intelligence";
import { formatCurrency, formatNumber } from "@/lib/utils";

export default async function RecommendationsPage() {
  const items = await getRecommendations();
  const totalRevenue = items.reduce((sum, i) => sum + i.estimatedRevenue, 0);
  const highImpact = items.filter((i) => i.impact === "High").length;
  const reach = items.reduce((max, i) => Math.max(max, i.audienceSize), 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Recommendations"
        description="Next best actions for retention campaigns, upsell, cross-sell, and customer recovery, ranked by expected impact."
      />
      <DemoBanner />

      <section aria-label="Recommendation summary" className="grid gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Estimated revenue opportunity</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums text-emerald-700">{formatCurrency(totalRevenue)}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">High-impact actions</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{highImpact} of {items.length}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Largest audience</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatNumber(reach)} customers</p>
        </Card>
      </section>

      <RecommendationBoard items={items} />
    </div>
  );
}