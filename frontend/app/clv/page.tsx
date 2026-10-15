import { Suspense } from "react";
import { DataErrorState, DataSourceBanner, NoDataState, PageSkeleton, load } from "@/components/data-state";
import { NotAvailableCell, NotAvailableValue } from "@/components/not-available";
import { PageHeader } from "@/components/page-header";
import { ClvBySegmentChart } from "@/components/charts/dashboard-charts";
import { EmptyState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getClvOverview } from "@/lib/api/customer-intelligence";
import { formatCurrency, formatNumber, formatSignedPercent } from "@/lib/utils";

function growthLabel(growth: number) {
  if (growth >= 25) return { label: "High potential", variant: "success" as const };
  if (growth >= 0) return { label: "Moderate", variant: "info" as const };
  return { label: "Declining", variant: "danger" as const };
}

export default function ClvPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Customer Lifetime Value"
        description="Customer value to date, with predicted CLV and growth potential for every customer and segment."
      />
      <Suspense fallback={<PageSkeleton cards={3} />}>
        <ClvContent />
      </Suspense>
    </div>
  );
}

async function ClvContent() {
  const result = await load(getClvOverview);
  if (!result.ok) return <DataErrorState error={result.error} />;
  const { meta, averageClv, averagePredictedClv, segments, customers } = result.data;
  if (meta.source === "live" && !meta.asOf) return <NoDataState />;
  const live = meta.source === "live";
  const portfolioGrowth =
    averageClv && averagePredictedClv !== null ? ((averagePredictedClv - averageClv) / averageClv) * 100 : null;
  const rows = customers
    .map((c) => ({
      ...c,
      growth: c.predictedClv !== null && c.currentClv ? ((c.predictedClv - c.currentClv) / c.currentClv) * 100 : null,
    }))
    .sort((a, b) => (b.growth ?? b.currentClv) - (a.growth ?? a.currentClv));

  return (
    <>
      <DataSourceBanner meta={meta} />

      <section aria-label="CLV summary" className="grid gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Average current CLV</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{averageClv === null ? "—" : formatCurrency(averageClv)}</p>
          <p className="text-xs text-slate-500">{live ? "Revenue to date per customer" : "Weighted across all segments"}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Average predicted CLV</p>
          {averagePredictedClv === null ? (
            <NotAvailableValue />
          ) : (
            <>
              <p className="mt-2 text-2xl font-semibold tabular-nums">{formatCurrency(averagePredictedClv)}</p>
              <p className="text-xs text-slate-500">12-month forward forecast</p>
            </>
          )}
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Portfolio growth potential</p>
          {portfolioGrowth === null ? (
            <NotAvailableValue />
          ) : (
            <>
              <p className="mt-2 text-2xl font-semibold tabular-nums text-emerald-700">{formatSignedPercent(portfolioGrowth)}</p>
              <p className="text-xs text-slate-500">Predicted vs current CLV</p>
            </>
          )}
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>{live ? "Average CLV by segment" : "Current vs predicted CLV by segment"}</CardTitle>
          <CardDescription>
            {live
              ? "Revenue to date per customer in each segment. Predicted CLV will be added once a model is trained (Phase 4)."
              : "Champions and Potential Loyalists are expanding; At-Risk and Lost customers are contracting."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {segments.length > 0 ? (
            <ClvBySegmentChart data={segments} />
          ) : (
            <EmptyState title="Not enough customers to segment" description="Segmentation needs at least 20 customers." />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{live ? "Customer CLV" : "Customer CLV forecast"}</CardTitle>
          <CardDescription>
            {live
              ? `Highest value first${customers.length < meta.customerCount ? ` (top ${formatNumber(customers.length)} of ${formatNumber(meta.customerCount)})` : ""}.`
              : "Sorted by growth potential. Negative growth flags customers to retain."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <caption className="sr-only">Current CLV, predicted CLV, and growth potential per customer</caption>
              <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="px-3 py-3 font-medium">Customer</th>
                  <th scope="col" className="px-3 py-3 font-medium">Segment</th>
                  <th scope="col" className="px-3 py-3 text-right font-medium">Current CLV</th>
                  <th scope="col" className="px-3 py-3 text-right font-medium">Predicted CLV</th>
                  <th scope="col" className="px-3 py-3 text-right font-medium">Change</th>
                  <th scope="col" className="px-3 py-3 font-medium">Growth potential</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const status = row.growth !== null ? growthLabel(row.growth) : null;
                  return (
                    <tr key={row.id} className="border-b border-slate-100 last:border-0">
                      <td className="px-3 py-3 font-medium text-slate-900">{row.name}</td>
                      <td className="px-3 py-3 text-slate-700">{row.segment ?? <span className="text-slate-400">Not segmented</span>}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{formatCurrency(row.currentClv)}</td>
                      <td className="px-3 py-3 text-right tabular-nums">
                        {row.predictedClv === null ? <NotAvailableCell /> : formatCurrency(row.predictedClv)}
                      </td>
                      <td
                        className={
                          row.growth === null
                            ? "px-3 py-3 text-right"
                            : row.growth >= 0
                              ? "px-3 py-3 text-right font-medium tabular-nums text-emerald-700"
                              : "px-3 py-3 text-right font-medium tabular-nums text-rose-700"
                        }
                      >
                        {row.growth === null ? <NotAvailableCell /> : formatSignedPercent(row.growth)}
                      </td>
                      <td className="px-3 py-3">
                        {status ? <Badge variant={status.variant}>{status.label}</Badge> : <NotAvailableCell />}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </>
  );
}
