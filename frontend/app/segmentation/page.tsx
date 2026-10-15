import { Suspense } from "react";
import { CustomerExplorer } from "@/components/customer-explorer";
import { DataErrorState, DataSourceBanner, NoDataState, PageSkeleton, load } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { SegmentDonutChart, SegmentRevenueBars } from "@/components/charts/dashboard-charts";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getCustomers, getSegments } from "@/lib/api/customer-intelligence";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";

export default function SegmentationPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Customer Segmentation"
        description="Customers grouped by recency, frequency, and spend (RFM) into Champions, Loyal Customers, Potential Loyalists, At-Risk Customers, and Lost Customers."
      />
      <Suspense fallback={<PageSkeleton cards={5} />}>
        <SegmentationContent />
      </Suspense>
    </div>
  );
}

async function SegmentationContent() {
  const result = await load(() => Promise.all([getSegments(), getCustomers()]));
  if (!result.ok) return <DataErrorState error={result.error} />;
  const [{ meta, segments }, { customers, total }] = result.data;
  if (meta.source === "live" && !meta.asOf) return <NoDataState />;
  const live = meta.source === "live";
  const totalCustomers = segments.reduce((sum, s) => sum + s.customers, 0);
  const totalRevenue = segments.reduce((sum, s) => sum + s.revenue, 0);
  const share = (part: number, whole: number) => formatPercent(whole ? (part / whole) * 100 : 0);

  return (
    <>
      <DataSourceBanner meta={meta} />

      {segments.length === 0 ? (
        <EmptyState
          title="Not enough customers to segment"
          description={`Segmentation compares customers with each other and needs at least 20. You have ${formatNumber(meta.customerCount)}.`}
        />
      ) : (
        <>
          <section aria-label="Segments" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {segments.map((segment) => (
              <Card key={segment.name} className="flex flex-col p-4">
                <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: segment.color }} aria-hidden="true" />
                  {segment.name}
                </p>
                <p className="mt-2 text-2xl font-semibold tabular-nums">{formatNumber(segment.customers)}</p>
                <p className="text-xs text-slate-500">
                  {share(segment.customers, totalCustomers)} of customers · {share(segment.revenue, totalRevenue)} of revenue
                </p>
                <dl className="mt-3 space-y-1 text-xs">
                  <div className="flex justify-between gap-2">
                    <dt className="text-slate-500">Revenue</dt>
                    <dd className="font-medium tabular-nums">{formatCurrency(segment.revenue)}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-slate-500">Avg CLV</dt>
                    <dd className="font-medium tabular-nums">{formatCurrency(segment.avgClv)}</dd>
                  </div>
                </dl>
                <p className="mt-3 border-t border-slate-100 pt-3 text-xs text-slate-600">{segment.definition}</p>
                <p className="mt-1 text-xs font-medium text-teal-800">{segment.strategy}</p>
              </Card>
            ))}
          </section>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Customers by segment</CardTitle>
                <CardDescription>Distribution of {formatNumber(totalCustomers)} customers.</CardDescription>
              </CardHeader>
              <CardContent>
                <SegmentDonutChart data={segments} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Revenue by segment</CardTitle>
                <CardDescription>Total revenue to date from each segment.</CardDescription>
              </CardHeader>
              <CardContent>
                <SegmentRevenueBars data={segments} />
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {live ? (
        <p className="text-xs text-slate-500">
          How segments are assigned: each customer gets 1–5 scores for recency (R), frequency (F), and
          spend (M) by ranking against all customers; FM is the rounded average of F and M. Champions:
          R≥4 and FM≥4 · Loyal: R≥3 and FM≥3 · Potential Loyalists: other R≥3 · At-Risk: R≤2 and FM≥3 ·
          Lost: the rest. Scores are relative, so segments shift as your customer base changes.
        </p>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Customer roster</CardTitle>
          <CardDescription>
            Search and filter customers by segment and {live ? "inactivity" : "churn risk"}.
            {total > customers.length ? ` Showing the top ${formatNumber(customers.length)} of ${formatNumber(total)} by revenue.` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CustomerExplorer
            customers={customers}
            caption="Customers with segment, health, CLV, and risk level"
            riskLabel={live ? "Inactivity" : "Churn risk"}
          />
        </CardContent>
      </Card>
    </>
  );
}
