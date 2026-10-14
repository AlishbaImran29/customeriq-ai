import { CustomerExplorer } from "@/components/customer-explorer";
import { DemoBanner } from "@/components/demo-banner";
import { PageHeader } from "@/components/page-header";
import { SegmentDonutChart, SegmentRevenueBars } from "@/components/charts/dashboard-charts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getCustomers, getSegments } from "@/lib/api/customer-intelligence";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";

export default async function SegmentationPage() {
  const [segments, customers] = await Promise.all([getSegments(), getCustomers()]);
  const totalCustomers = segments.reduce((sum, s) => sum + s.customers, 0);
  const totalRevenue = segments.reduce((sum, s) => sum + s.revenue, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Customer Segmentation"
        description="Customers grouped by recency, frequency, and spend into Champions, Loyal Customers, Potential Loyalists, At-Risk Customers, and Lost Customers."
      />
      <DemoBanner />

      <section aria-label="Segments" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {segments.map((segment) => (
          <Card key={segment.name} className="flex flex-col p-4">
            <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: segment.color }} aria-hidden="true" />
              {segment.name}
            </p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">{formatNumber(segment.customers)}</p>
            <p className="text-xs text-slate-500">
              {formatPercent((segment.customers / totalCustomers) * 100)} of customers ·{" "}
              {formatPercent((segment.revenue / totalRevenue) * 100)} of revenue
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
            <CardDescription>Champions contribute the largest share of revenue.</CardDescription>
          </CardHeader>
          <CardContent>
            <SegmentRevenueBars data={segments} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Customer roster</CardTitle>
          <CardDescription>Search and filter customers by segment and churn risk.</CardDescription>
        </CardHeader>
        <CardContent>
          <CustomerExplorer customers={customers} caption="Customers with segment, health, CLV, and churn risk" />
        </CardContent>
      </Card>
    </div>
  );
}