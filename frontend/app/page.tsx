import Link from "next/link";
import {
  Activity,
  ArrowRight,
  HeartPulse,
  Sparkles,
  TrendingUp,
  Users,
  Wallet,
} from "lucide-react";
import { DemoBanner } from "@/components/demo-banner";
import { KpiCard } from "@/components/kpi-card";
import { PageHeader } from "@/components/page-header";
import { RevenueForecastChart, SegmentDonutChart } from "@/components/charts/dashboard-charts";
import { Badge, impactVariant, riskVariant } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getOverview } from "@/lib/api/customer-intelligence";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";

export default async function OverviewPage() {
  const { kpis, kpiDeltas, executiveSummary, revenueSeries, segments, topRecommendations, atRiskCustomers } =
    await getOverview();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Customer Intelligence Dashboard"
        description="Customer performance and business health at a glance: segmentation, churn risk, lifetime value, and growth opportunities."
      />
      <DemoBanner />

      <section aria-label="Key metrics" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <KpiCard label="Total Customers" value={formatNumber(kpis.totalCustomers)} delta={kpiDeltas.totalCustomers} icon={Users} />
        <KpiCard label="Revenue" value={formatCurrency(kpis.revenue)} delta={kpiDeltas.revenue} icon={TrendingUp} />
        <KpiCard label="Customer Lifetime Value" value={formatCurrency(kpis.averageClv)} delta={kpiDeltas.averageClv} icon={Wallet} />
        <KpiCard label="Retention Rate" value={formatPercent(kpis.retentionRate)} delta={kpiDeltas.retentionRate} icon={HeartPulse} />
        <KpiCard label="Churn Risk" value={formatPercent(kpis.churnRisk)} delta={kpiDeltas.churnRisk} invertDelta icon={Activity} />
        <KpiCard label="Growth Score" value={`${kpis.growthScore}/100`} delta={kpiDeltas.growthScore} icon={Sparkles} />
      </section>

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Revenue trend & forecast</CardTitle>
            <CardDescription>Monthly revenue with a three-month forecast and confidence range.</CardDescription>
          </CardHeader>
          <CardContent>
            <RevenueForecastChart data={revenueSeries} />
          </CardContent>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Segment mix</CardTitle>
            <CardDescription>Share of customers in each segment.</CardDescription>
          </CardHeader>
          <CardContent>
            <SegmentDonutChart data={segments} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-teal-600" aria-hidden="true" />
              Executive summary
            </CardTitle>
            <CardDescription>{executiveSummary.headline}</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm text-slate-600">
              {executiveSummary.bullets.map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-600" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Next best actions</CardTitle>
            <CardDescription>Highest-impact recommendations right now.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {topRecommendations.map((item) => (
              <div key={item.id} className="rounded-xl border border-slate-100 p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium text-slate-900">{item.title}</p>
                  <Badge variant={impactVariant(item.impact)}>{item.impact}</Badge>
                </div>
                <p className="mt-1 text-xs text-slate-500">{item.nextAction}</p>
              </div>
            ))}
            <Link href="/recommendations" className="inline-flex items-center gap-1 text-sm font-medium text-teal-700 hover:text-teal-800">
              All recommendations <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Customers most likely to churn</CardTitle>
            <CardDescription>Ranked by predicted churn probability.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-slate-100">
              {atRiskCustomers.map((customer) => (
                <li key={customer.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-900">{customer.name}</p>
                    <p className="truncate text-xs text-slate-500">{customer.segment}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-sm font-semibold tabular-nums">{formatPercent(customer.churnProbability, 0)}</span>
                    <Badge variant={riskVariant(customer.riskLevel)}>{customer.riskLevel}</Badge>
                  </div>
                </li>
              ))}
            </ul>
            <Link href="/churn" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-teal-700 hover:text-teal-800">
              View churn predictions <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}