import { Suspense } from "react";
import { Activity, CalendarClock, MousePointerClick, ShoppingBag } from "lucide-react";
import { DataErrorState, DataSourceBanner, NoDataState, PageSkeleton, load } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { HealthDistributionChart } from "@/components/charts/dashboard-charts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, scoreTone } from "@/components/ui/progress";
import { getHealthOverview } from "@/lib/api/customer-intelligence";
import type { HealthFactors } from "@/lib/types";
import { formatNumber } from "@/lib/utils";

const factors: { key: keyof HealthFactors; label: string; description: string; icon: typeof Activity }[] = [
  { key: "purchaseFrequency", label: "Purchase frequency", description: "Orders per active month, ranked against all customers", icon: ShoppingBag },
  { key: "spendingBehavior", label: "Spending behavior", description: "Spend in the last 12 months, ranked against all customers", icon: Activity },
  { key: "engagement", label: "Customer engagement", description: "Average of the imported engagement scores (0–100)", icon: MousePointerClick },
  { key: "activityTrend", label: "Activity trend", description: "Time since last order vs the customer's usual gap", icon: CalendarClock },
];

export default function HealthPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Customer Health Score"
        description="A 0–100 score combining purchase frequency, spending behavior, customer engagement, and activity trends."
      />
      <Suspense fallback={<PageSkeleton cards={4} />}>
        <HealthContent />
      </Suspense>
    </div>
  );
}

async function HealthContent() {
  const result = await load(getHealthOverview);
  if (!result.ok) return <DataErrorState error={result.error} />;
  const { meta, weights, weightsWithoutEngagement, distribution, customers } = result.data;
  if (meta.source === "live" && !meta.asOf) return <NoDataState />;
  const missingEngagement = customers.filter((c) => c.engagementMissing).length;

  return (
    <>
      <DataSourceBanner meta={meta} />

      <Card>
        <CardHeader>
          <CardTitle>How the score is calculated</CardTitle>
          <CardDescription>Each factor is scaled to 0–100 and weighted.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {factors.map((factor) => (
              <li key={factor.key} className="rounded-xl border border-line/60 p-3">
                <div className="flex items-center justify-between gap-2">
                  <factor.icon className="h-4 w-4 text-accent" aria-hidden="true" />
                  <span className="text-lg font-semibold tabular-nums">
                    {Math.round(weights[factor.key] * 100)}%
                    {weightsWithoutEngagement ? (
                      <span className="ml-1 text-xs font-normal text-muted">
                        / {Math.round(weightsWithoutEngagement[factor.key] * 1000) / 10}%
                      </span>
                    ) : null}
                  </span>
                </div>
                <p className="mt-2 text-sm font-medium text-ink">{factor.label}</p>
                <p className="text-xs text-muted">{factor.description}</p>
              </li>
            ))}
          </ul>
          {weightsWithoutEngagement ? (
            <p className="mt-4 text-xs text-muted">
              The second percentage is used when a customer has <strong>no engagement data</strong>:
              engagement is left out (never counted as 0) and the other weights are scaled up.
              {missingEngagement > 0
                ? ` ${formatNumber(missingEngagement)} of the customers listed below are scored this way.`
                : ""}{" "}
              Activity trend is 100 within the usual gap between orders and 0 at three times that gap or
              more; single-order customers use a 90-day gap.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Health distribution</CardTitle>
            <CardDescription>Customers in each health band.</CardDescription>
          </CardHeader>
          <CardContent>
            <HealthDistributionChart data={distribution} />
          </CardContent>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Bands</CardTitle>
            <CardDescription>Score ranges and customer counts.</CardDescription>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <caption className="sr-only">Customers per health band</caption>
              <thead className="text-xs uppercase tracking-wide text-muted">
                <tr className="border-b border-line">
                  <th scope="col" className="py-2 text-left font-medium">Band</th>
                  <th scope="col" className="py-2 text-left font-medium">Score</th>
                  <th scope="col" className="py-2 text-right font-medium">Customers</th>
                </tr>
              </thead>
              <tbody>
                {distribution.map((bucket) => (
                  <tr key={bucket.label} className="border-b border-line/60 last:border-0">
                    <td className="py-2.5 font-medium text-ink">{bucket.label}</td>
                    <td className="py-2.5 text-ink-2">{bucket.range}</td>
                    <td className="py-2.5 text-right tabular-nums">{formatNumber(bucket.customers)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Health drivers by customer</CardTitle>
          <CardDescription>Lowest scores first, so the customers needing attention appear at the top.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[880px] text-left text-sm">
              <caption className="sr-only">Health score and factor breakdown per customer</caption>
              <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th scope="col" className="px-3 py-3 font-medium">Customer</th>
                  <th scope="col" className="px-3 py-3 font-medium">Health</th>
                  {factors.map((f) => (
                    <th key={f.key} scope="col" className="px-3 py-3 font-medium">{f.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {customers.map((row) => (
                  <tr key={row.id} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-3">
                      <p className="font-medium text-ink">{row.name}</p>
                      <p className="text-xs text-muted">{row.segment ?? "Not segmented"}</p>
                    </td>
                    <td className="px-3 py-3 text-lg font-semibold tabular-nums">{row.healthScore}</td>
                    {factors.map((f) => {
                      const value = row.healthFactors[f.key];
                      return (
                        <td key={f.key} className="px-3 py-3">
                          {value === null ? (
                            <span className="text-xs text-faint">No data · re-weighted</span>
                          ) : (
                            <div className="flex items-center gap-2">
                              <Progress value={value} tone={scoreTone(value)} label={`${row.name} ${f.label}`} className="w-20" />
                              <span className="w-7 text-xs tabular-nums text-ink-2">{value}</span>
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </>
  );
}
