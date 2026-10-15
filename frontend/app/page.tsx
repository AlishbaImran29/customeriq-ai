import { Suspense } from "react";
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
import {
  DataErrorState,
  DataSourceBanner,
  ModelNote,
  NoDataState,
  PageSkeleton,
  load,
  reasonFor,
} from "@/components/data-state";
import { KpiCard } from "@/components/kpi-card";
import { PageHeader } from "@/components/page-header";
import { RevenueForecastChart, SegmentDonutChart } from "@/components/charts/dashboard-charts";
import { EmptyState } from "@/components/states";
import { Badge, impactVariant, riskVariant } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getOverview } from "@/lib/api/customer-intelligence";
import type { GrowthScoreDetails } from "@/lib/types";
import { Money } from "@/components/money";
import { formatNumber, formatPercent } from "@/lib/utils";


function GrowthScoreExplainer({ details }: { details: GrowthScoreDetails }) {
  return (
    <details className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
      <summary className="cursor-pointer font-medium text-slate-900">
        How the Growth Score ({details.score}/100) is calculated
      </summary>
      <p className="mt-2 text-xs text-slate-500">
        It is <strong>our own</strong> weighted average of the measured inputs below, not an industry standard and
        not a prediction. Revenue growth −50% to +50% maps to 0–100; customer growth −20% to +20% maps to 0–100.
        {details.missing.length > 0
          ? ` Left out for now (not enough history): ${details.missing.join("; ")}. The other weights are scaled up.`
          : ""}
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-sm">
          <caption className="sr-only">Growth Score inputs, their measured values, scores, and weights</caption>
          <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th scope="col" className="py-2 pr-3 font-medium">Input</th>
              <th scope="col" className="px-3 py-2 font-medium">Measured</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Score (0–100)</th>
              <th scope="col" className="py-2 pl-3 text-right font-medium">Weight</th>
            </tr>
          </thead>
          <tbody>
            {details.components.map((item) => (
              <tr key={item.key} className="border-b border-slate-100 last:border-0">
                <td className="py-2 pr-3">{item.label}</td>
                <td className="px-3 py-2 tabular-nums">{item.measure}</td>
                <td className="px-3 py-2 text-right tabular-nums">{item.value}</td>
                <td className="py-2 pl-3 text-right tabular-nums">{item.weight}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export default function OverviewPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Customer Intelligence Dashboard"
        description="Customer performance and business health at a glance: segmentation, churn risk, lifetime value, and growth opportunities."
      />
      <Suspense fallback={<PageSkeleton cards={6} />}>
        <OverviewContent />
      </Suspense>
    </div>
  );
}

async function OverviewContent() {
  const result = await load(getOverview);
  if (!result.ok) return <DataErrorState error={result.error} />;
  const {
    meta,
    kpis,
    kpiDeltas,
    growthScoreDetails,
    executiveSummary,
    revenueSeries,
    segments,
    topRecommendations,
    atRiskCustomers,
  } = result.data;
  if (meta.source === "live" && !meta.asOf) return <NoDataState />;
  const live = meta.source === "live";
  const churnPredicted = meta.models.churn.status === "available";
  const forecastPredicted = meta.models.forecast.status === "available";
  const value = (v: number | null, format: (n: number) => React.ReactNode) => (v === null ? null : format(v));
  const money = (n: number) => <Money value={n} />;

  return (
    <>
      <DataSourceBanner meta={meta} />

      <ModelNote model={meta.models.churn} title="Churn model" />
      <ModelNote model={meta.models.forecast} title="Revenue forecast" />

      <section aria-label="Key metrics" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <KpiCard label="Total Customers" value={value(kpis.totalCustomers, formatNumber)} delta={kpiDeltas.totalCustomers} icon={Users} />
        <KpiCard
          label={live ? "Revenue (last 90 days)" : "Revenue"}
          value={value(kpis.revenue, money)}
          delta={kpiDeltas.revenue}
          icon={TrendingUp}
        />
        <KpiCard
          label={live ? "Customer Lifetime Value (to date)" : "Customer Lifetime Value"}
          value={value(kpis.averageClv, money)}
          delta={kpiDeltas.averageClv}
          icon={Wallet}
        />
        <KpiCard
          label={live ? "Retention Rate (90 days)" : "Retention Rate"}
          value={value(kpis.retentionRate, formatPercent)}
          delta={kpiDeltas.retentionRate}
          deltaUnit="pts"
          unavailableReason="Needs at least 180 days of order history."
          icon={HeartPulse}
        />
        <KpiCard
          label={live ? "Predicted Churn Risk" : "Churn Risk"}
          value={value(kpis.churnRisk, formatPercent)}
          delta={kpiDeltas.churnRisk}
          deltaUnit="pts"
          invertDelta
          unavailableReason={reasonFor(meta, "churnRisk")}
          note="Model estimate: average chance of no order in the next 90 days"
          icon={Activity}
        />
        <KpiCard
          label="Growth Score"
          value={value(kpis.growthScore, (n) => `${n}/100`)}
          delta={kpiDeltas.growthScore}
          deltaUnit="pts"
          unavailableReason={reasonFor(meta, "growthScore")}
          note={live ? "Our own score from measured metrics (see below)" : "Sample score"}
          icon={Sparkles}
        />
      </section>

      {growthScoreDetails ? <GrowthScoreExplainer details={growthScoreDetails} /> : null}

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>{forecastPredicted ? "Revenue trend & forecast" : "Revenue trend"}</CardTitle>
            <CardDescription>
              {!live
                ? "Monthly revenue with a three-month forecast and confidence range."
                : forecastPredicted
                  ? "Monthly revenue from your orders with a 3-month trend forecast (model estimate, shaded 80% range). The last month may be partial."
                  : `Monthly revenue from your orders. The last month may be partial (month to date). Forecast not shown: ${reasonFor(meta, "revenueForecast") ?? "not available."}`}
            </CardDescription>
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
            {segments.length > 0 ? (
              <SegmentDonutChart data={segments} />
            ) : (
              <EmptyState title="Not enough customers to segment" description="Segmentation needs at least 20 customers." />
            )}
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
            <p className="mt-3 text-xs text-slate-400">
              {executiveSummary.method === "rules"
                ? "Generated from your data with fixed rules (no AI)."
                : "Sample summary for the demo."}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Next best actions</CardTitle>
            <CardDescription>{live ? "Rule-based actions for your largest segments." : "Highest-impact recommendations right now."}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {topRecommendations.length === 0 ? (
              <p className="text-sm text-slate-500">Recommendations appear once customers can be segmented (20+ customers).</p>
            ) : (
              topRecommendations.map((item) => (
                <div key={item.id} className="rounded-xl border border-slate-100 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium text-slate-900">{item.title}</p>
                    <Badge variant={impactVariant(item.impact)}>{item.impact}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{item.nextAction}</p>
                </div>
              ))
            )}
            <Link href="/recommendations" className="inline-flex items-center gap-1 text-sm font-medium text-teal-700 hover:text-teal-800">
              All recommendations <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              {!live ? "Customers most likely to churn" : churnPredicted ? "Valuable customers likely to leave" : "Valuable customers going quiet"}
            </CardTitle>
            <CardDescription>
              {!live
                ? "Ranked by predicted churn probability."
                : churnPredicted
                  ? "Highest expected revenue loss: predicted chance of leaving × 12-month spend. Model estimate."
                  : "At-Risk customers with the highest spend in the last 12 months. Inactivity is rule-based, not a prediction."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {atRiskCustomers.length === 0 ? (
              <p className="text-sm text-slate-500">No At-Risk customers right now.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {atRiskCustomers.map((customer) => (
                  <li key={customer.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-900">{customer.name}</p>
                      <p className="truncate text-xs text-slate-500">
                        {customer.segment ?? "Not segmented"}
                        {customer.daysSinceLastOrder !== undefined ? ` · last order ${customer.daysSinceLastOrder} days ago` : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="text-sm font-semibold tabular-nums">
                        {customer.churnProbability !== null
                          ? formatPercent(customer.churnProbability, 0)
                          : <Money value={customer.revenue} />}
                      </span>
                      <Badge variant={riskVariant(customer.riskLevel)}>{customer.riskLevel}</Badge>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <Link href="/churn" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-teal-700 hover:text-teal-800">
              {churnPredicted ? "View churn predictions" : "View inactivity levels"} <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
