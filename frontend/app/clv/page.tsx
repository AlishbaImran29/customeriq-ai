import { Suspense } from "react";
import { DataErrorState, DataSourceBanner, ModelNote, NoDataState, PageSkeleton, load } from "@/components/data-state";
import { NotAvailableCell, NotAvailableValue } from "@/components/not-available";
import { PageHeader } from "@/components/page-header";
import { ClvBySegmentChart } from "@/components/charts/dashboard-charts";
import { EmptyState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getClvOverview } from "@/lib/api/customer-intelligence";
import { Money } from "@/components/money";
import { formatNumber, formatSignedPercent } from "@/lib/utils";

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
  const predicted = meta.models.clv.status === "available";
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
      <ModelNote model={meta.models.clv} title="Predicted CLV" />
      {!predicted ? (
        <p className="rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink-2">
          <strong className="text-ink">Predicted CLV is not available.</strong>{" "}
          {meta.models.clv.reason} Current CLV below is actual revenue to date.
        </p>
      ) : live ? (
        <p className="text-xs text-muted">
          Predicted CLV = revenue to date + the model&apos;s estimate of spend over the next 6 months.
        </p>
      ) : null}

      <section aria-label="CLV summary" className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Average current CLV</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{averageClv === null ? "—" : <Money value={averageClv} />}</p>
          <p className="text-xs text-muted">{live ? "Revenue to date per customer" : "Weighted across all segments"}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Average predicted CLV</p>
          {averagePredictedClv === null ? (
            <NotAvailableValue reason={meta.models.clv.reason ?? undefined} />
          ) : (
            <>
              <p className="mt-2 text-2xl font-semibold tabular-nums"><Money value={averagePredictedClv} /></p>
              <p className="text-xs text-muted">12-month forward forecast</p>
            </>
          )}
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Portfolio growth potential</p>
          {portfolioGrowth === null ? (
            <NotAvailableValue reason={meta.models.clv.reason ?? undefined} />
          ) : (
            <>
              <p className="mt-2 text-2xl font-semibold tabular-nums text-success">{formatSignedPercent(portfolioGrowth)}</p>
              <p className="text-xs text-muted">Predicted vs current CLV</p>
            </>
          )}
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>{predicted ? "Current vs predicted CLV by segment" : "Average CLV by segment"}</CardTitle>
          <CardDescription>
            {!live
              ? "Champions and Potential Loyalists are expanding; At-Risk and Lost customers are contracting."
              : predicted
                ? "Average revenue to date per customer in each segment, next to the model's predicted CLV."
                : "Revenue to date per customer in each segment."}
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
          <CardTitle>{predicted ? "Customer CLV forecast" : "Customer CLV"}</CardTitle>
          <CardDescription>
            {predicted
              ? "Sorted by growth potential. Negative growth flags customers to retain."
              : `Highest value first${customers.length < meta.customerCount ? ` (top ${formatNumber(customers.length)} of ${formatNumber(meta.customerCount)})` : ""}.`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <caption className="sr-only">Current CLV, predicted CLV, and growth potential per customer</caption>
              <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
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
                    <tr key={row.id} className="border-b border-line/60 last:border-0">
                      <td className="px-3 py-3 font-medium text-ink">{row.name}</td>
                      <td className="px-3 py-3 text-ink-2">{row.segment ?? <span className="text-faint">Not segmented</span>}</td>
                      <td className="px-3 py-3 text-right tabular-nums"><Money value={row.currentClv} /></td>
                      <td className="px-3 py-3 text-right tabular-nums">
                        {row.predictedClv === null ? <NotAvailableCell /> : <Money value={row.predictedClv} />}
                      </td>
                      <td
                        className={
                          row.growth === null
                            ? "px-3 py-3 text-right"
                            : row.growth >= 0
                              ? "px-3 py-3 text-right font-medium tabular-nums text-success"
                              : "px-3 py-3 text-right font-medium tabular-nums text-danger"
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
