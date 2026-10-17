import { Suspense } from "react";
import { DataErrorState, DataSourceBanner, NoDataState, PageSkeleton, load } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { RecommendationBoard } from "@/components/recommendation-board";
import { EmptyState } from "@/components/states";
import { Card } from "@/components/ui/card";
import { getRecommendations } from "@/lib/api/customer-intelligence";
import { Money } from "@/components/money";
import { formatNumber } from "@/lib/utils";

export default function RecommendationsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Recommendations"
        description="Next best actions for retention campaigns, upsell, cross-sell, and customer recovery, ranked by impact."
      />
      <Suspense fallback={<PageSkeleton cards={3} />}>
        <RecommendationsContent />
      </Suspense>
    </div>
  );
}

async function RecommendationsContent() {
  const result = await load(getRecommendations);
  if (!result.ok) return <DataErrorState error={result.error} />;
  const { meta, items } = result.data;
  if (meta.source === "live" && !meta.asOf) return <NoDataState />;
  const live = meta.source === "live";
  const totalRevenue = items.reduce(
    (sum, i) => sum + (live ? (i.historicalRevenue ?? 0) : (i.estimatedRevenue ?? 0)),
    0,
  );
  const highImpact = items.filter((i) => i.impact === "High").length;
  const reach = items.reduce((max, i) => Math.max(max, i.audienceSize), 0);

  return (
    <>
      <DataSourceBanner meta={meta} />
      {live ? (
        <p className="text-sm text-ink-2">
          These recommendations come from <strong>fixed rules per segment</strong>, not from an AI
          model. Impact is based on each audience&apos;s share of the last 12 months&apos; revenue
          (High ≥ 20%, Medium ≥ 8%). No revenue gains are estimated, because that needs a trained
          model.
        </p>
      ) : null}

      {items.length === 0 ? (
        <EmptyState
          title="No recommendations yet"
          description="Recommendations are based on segments, which need at least 20 customers."
        />
      ) : (
        <>
          <section aria-label="Recommendation summary" className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Card className="p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">
                {live ? "Spent by target audiences (12 mo)" : "Estimated revenue opportunity"}
              </p>
              <p className={live ? "mt-2 text-2xl font-semibold tabular-nums" : "mt-2 text-2xl font-semibold tabular-nums text-success"}>
                <Money value={totalRevenue} />
              </p>
              {live ? <p className="text-xs text-muted">Historical spend, not a forecast</p> : null}
            </Card>
            <Card className="p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">High-impact actions</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums">{highImpact} of {items.length}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">Largest audience</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums">{formatNumber(reach)} customers</p>
            </Card>
          </section>
          <RecommendationBoard items={items} />
        </>
      )}
    </>
  );
}
