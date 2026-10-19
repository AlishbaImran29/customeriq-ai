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
import { ChannelFilter } from "@/components/channel-filter";
import { ChannelRevenueCard } from "@/components/channel-revenue-card";
import { KpiCard } from "@/components/kpi-card";
import { NeedMoreCustomers, NoOrdersInChannel } from "@/components/need-more-data";
import { OrderRiskCard } from "@/components/order-risk-card";
import { PageHeader } from "@/components/page-header";
import { DateRangePicker } from "@/components/date-range-picker";
import { dayCount, formatRange, lastDays, rangeFromParams } from "@/lib/dates";
import { RevenueForecastChart, SegmentDonutChart } from "@/components/charts/dashboard-charts";
import { EmptyState } from "@/components/states";
import { Badge, impactVariant, riskVariant } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getOverview } from "@/lib/api/customer-intelligence";
import { CHANNELS } from "@/lib/quick-order";
import type { GrowthScoreDetails } from "@/lib/types";
import { Money } from "@/components/money";
import { formatNumber, formatPercent } from "@/lib/utils";


function GrowthScoreExplainer({ details }: { details: GrowthScoreDetails }) {
  return (
    <details className="rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink-2">
      <summary className="cursor-pointer font-medium text-ink">
        How the Growth Score ({details.score}/100) is calculated
      </summary>
      <p className="mt-2 text-xs text-muted">
        It is <strong>our own</strong> weighted average of the measured inputs below, not an industry standard and
        not a prediction. Revenue growth −50% to +50% maps to 0–100; customer growth −20% to +20% maps to 0–100.
        {details.missing.length > 0
          ? ` Left out for now (not enough history): ${details.missing.join("; ")}. The other weights are scaled up.`
          : ""}
      </p>
      <div className="relative mt-3 overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-sm">
          <caption className="sr-only">Growth Score inputs, their measured values, scores, and weights</caption>
          <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
            <tr>
              <th scope="col" className="py-2 pr-3 font-medium">Input</th>
              <th scope="col" className="px-3 py-2 font-medium">Measured</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Score (0–100)</th>
              <th scope="col" className="py-2 pl-3 text-right font-medium">Weight</th>
            </tr>
          </thead>
          <tbody>
            {details.components.map((item) => (
              <tr key={item.key} className="border-b border-line/60 last:border-0">
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

export default function OverviewPage({ searchParams }: { searchParams: Promise<{ from?: string; to?: string; channel?: string }> }) {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Customer Intelligence Dashboard"
        description="Customer performance and business health at a glance: segmentation, churn risk, lifetime value, and growth opportunities."
      />
      <Suspense fallback={<PageSkeleton cards={6} />}>
        <OverviewContent searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function OverviewContent({ searchParams }: { searchParams: Promise<{ from?: string; to?: string; channel?: string }> }) {
  const params = await searchParams;
  const range = rangeFromParams(params.from, params.to);
  const channel = CHANNELS.find((c) => c.value === params.channel)?.value;
  const result = await load(() => getOverview(range ?? undefined, channel));
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
    revenueByChannel,
    channelPeriodStart,
    channelPeriodEnd,
    segmentsNeeded,
  } = result.data;
  if (meta.source === "live" && !meta.asOf) {
    // A channel with no orders is not "no data": say so, and keep the filter so the seller can go back.
    if (channel) {
      return (
        <>
          <ChannelFilter current={channel} channels={revenueByChannel} keep={{ from: params.from, to: params.to }} />
          <NoOrdersInChannel channel={CHANNELS.find((c) => c.value === channel)?.label ?? channel} />
        </>
      );
    }
    return <NoDataState />;
  }
  const live = meta.source === "live";
  const churnPredicted = meta.models.churn.status === "available";
  const forecastPredicted = meta.models.forecast.status === "available";
  const value = (v: number | null, format: (n: number) => React.ReactNode) => (v === null ? null : format(v));
  const money = (n: number) => <Money value={n} />;

  return (
    <>
      <DataSourceBanner meta={meta} />

      {live && revenueByChannel.length > 0 ? (
        <ChannelFilter current={channel ?? null} channels={revenueByChannel} keep={{ from: params.from, to: params.to }} />
      ) : null}

      {live && meta.asOf ? <DateRangePicker asOf={meta.asOf} current={range ?? lastDays(meta.asOf, 90)} /> : null}

      <ModelNote model={meta.models.churn} title="Churn model" />
      <ModelNote model={meta.models.forecast} title="Revenue forecast" />

      <section aria-label="Key metrics" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <KpiCard label="Total Customers" value={value(kpis.totalCustomers, formatNumber)} delta={kpiDeltas.totalCustomers} icon={Users} />
        <KpiCard
          label={live ? (range ? `Revenue (${formatRange(range)})` : "Revenue (last 90 days)") : "Revenue"}
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
          label={live ? (range ? `Retention Rate (${dayCount(range)} days)` : "Retention Rate (90 days)") : "Retention Rate"}
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

      {live ? (
        <Suspense fallback={null}>
          <OrderRiskCard />
        </Suspense>
      ) : null}

      {growthScoreDetails ? <GrowthScoreExplainer details={growthScoreDetails} /> : null}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
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
              segmentsNeeded > 0 ? (
                <NeedMoreCustomers needed={segmentsNeeded} minimum={meta.customerCount + segmentsNeeded} />
              ) : (
                <EmptyState title="Not enough customers to segment" description="Segmentation needs at least 20 customers." />
              )
            )}
          </CardContent>
        </Card>
      </div>

      {live && revenueByChannel.length > 0 ? (
        <ChannelRevenueCard channels={revenueByChannel} start={channelPeriodStart} end={channelPeriodEnd} />
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-accent" aria-hidden="true" />
              Executive summary
            </CardTitle>
            <CardDescription>{executiveSummary.headline}</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm text-ink-2">
              {executiveSummary.bullets.map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-faint">
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
              <p className="text-sm text-muted">Recommendations appear once customers can be segmented (20+ customers).</p>
            ) : (
              topRecommendations.map((item) => (
                <div key={item.id} className="rounded-xl border border-line/60 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium text-ink">{item.title}</p>
                    <Badge variant={impactVariant(item.impact)}>{item.impact}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted">{item.nextAction}</p>
                </div>
              ))
            )}
            <Link href="/recommendations" className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent">
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
              <p className="text-sm text-muted">No At-Risk customers right now.</p>
            ) : (
              <ul className="divide-y divide-line/60">
                {atRiskCustomers.map((customer) => (
                  <li key={customer.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink">{customer.name}</p>
                      <p className="truncate text-xs text-muted">
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
            <Link href="/churn" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent">
              {churnPredicted ? "View churn predictions" : "View inactivity levels"} <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
