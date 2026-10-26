import { Suspense } from "react";
import { DataErrorState, DataSourceBanner, NoDataState, PageSkeleton, load } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { ClvBySegmentChart } from "@/components/charts/dashboard-charts";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getClvOverview } from "@/lib/api/customer-intelligence";
import { Money } from "@/components/money";
import { formatNumber } from "@/lib/utils";

export default function ClvPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Customer Lifetime Value"
        description="What each customer and each segment has spent with you so far (historical lifetime value)."
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
  const { meta, averageClv, segments, customers } = result.data;
  if (meta.source === "live" && !meta.asOf) return <NoDataState />;
  const live = meta.source === "live";
  const rows = [...customers].sort((a, b) => b.currentClv - a.currentClv);

  return (
    <>
      <DataSourceBanner meta={meta} />
      <p className="rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink-2">
        <strong className="text-ink">Future CLV is not predicted.</strong> We tested a model for it, and on the Online Retail II data it
        was no more accurate than simply assuming a customer repeats their last 6 months, so it is not shown. The figures below are
        what customers actually spent.
      </p>

      <section aria-label="CLV summary" className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Average CLV to date</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{averageClv === null ? "—" : <Money value={averageClv} />}</p>
          <p className="text-xs text-muted">{live ? "Revenue to date per customer" : "Weighted across all segments"}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Customers</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatNumber(meta.customerCount)}</p>
          <p className="text-xs text-muted">With at least one order</p>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Average CLV by segment</CardTitle>
          <CardDescription>Revenue to date per customer in each segment.</CardDescription>
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
          <CardTitle>Customer CLV</CardTitle>
          <CardDescription>
            Highest value first{customers.length < meta.customerCount ? ` (top ${formatNumber(customers.length)} of ${formatNumber(meta.customerCount)})` : ""}.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-sm">
              <caption className="sr-only">Lifetime value to date per customer</caption>
              <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th scope="col" className="px-3 py-3 font-medium">Customer</th>
                  <th scope="col" className="px-3 py-3 font-medium">Segment</th>
                  <th scope="col" className="px-3 py-3 text-right font-medium">Orders</th>
                  <th scope="col" className="px-3 py-3 text-right font-medium">CLV to date</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-3 font-medium text-ink">{row.name}</td>
                    <td className="px-3 py-3 text-ink-2">{row.segment ?? <span className="text-faint">Not segmented</span>}</td>
                    <td className="px-3 py-3 text-right tabular-nums">{formatNumber(row.orders)}</td>
                    <td className="px-3 py-3 text-right tabular-nums"><Money value={row.currentClv} /></td>
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
