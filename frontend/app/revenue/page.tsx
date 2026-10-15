import { Suspense } from "react";
import { DataErrorState, DataSourceBanner, ModelNote, NoDataState, PageSkeleton, load, reasonFor } from "@/components/data-state";
import { NotAvailableValue } from "@/components/not-available";
import { PageHeader } from "@/components/page-header";
import { RevenueAtRiskCalculator, type CalculatorDefaults } from "@/components/revenue-at-risk-calculator";
import { RevenueAtRiskChart, RevenueForecastChart } from "@/components/charts/dashboard-charts";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { getRevenueOverview } from "@/lib/api/customer-intelligence";
import { Money } from "@/components/money";
import { formatNumber, formatPercent, formatSignedPercent } from "@/lib/utils";

export default function RevenuePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Revenue Intelligence"
        description="Revenue trends, forecasting, revenue drivers, and revenue-at-risk analysis for growth decisions."
      />
      <Suspense fallback={<PageSkeleton cards={4} />}>
        <RevenueContent />
      </Suspense>
    </div>
  );
}

async function RevenueContent() {
  const result = await load(getRevenueOverview);
  if (!result.ok) return <DataErrorState error={result.error} />;
  const { meta, series, atRiskTrend, atRiskBySegment, drivers } = result.data;
  if (meta.source === "live" && !meta.asOf) return <NoDataState />;
  const live = meta.source === "live";
  const forecastPredicted = meta.models.forecast.status === "available";

  const actuals = series.filter((p) => p.actual !== undefined);
  // Compare complete months only; a month still in progress would look like a drop.
  const complete = actuals.filter((p) => !p.partial);
  const latest = complete[complete.length - 1];
  const previous = complete[complete.length - 2];
  const monthChange = latest?.actual && previous?.actual ? ((latest.actual - previous.actual) / previous.actual) * 100 : null;
  const forecast = series.filter((p) => p.actual === undefined && p.forecast !== undefined);
  const forecastTotal = forecast.reduce((sum, p) => sum + (p.forecast ?? 0), 0);
  const totalAtRisk = atRiskBySegment.reduce((sum, s) => sum + s.atRisk, 0);
  const revenue12m = live ? (drivers[0]?.rows.reduce((sum, r) => sum + r.revenue, 0) ?? 0) : 0;
  const currentAtRisk = atRiskTrend?.[atRiskTrend.length - 1]?.atRisk ?? 0;
  const atRiskCustomerCount = atRiskBySegment.reduce((sum, s) => sum + s.customers, 0);
  // Live data: start from your At-Risk and Lost customers. Demo: made-up sample numbers.
  const calculatorDefaults: CalculatorDefaults =
    live && atRiskCustomerCount > 0
      ? {
          customers: atRiskCustomerCount,
          yearlySpend: totalAtRisk / atRiskCustomerCount,
          share: 50,
          source: `your ${atRiskCustomerCount.toLocaleString("en-US")} At-Risk and Lost customers (their spend over the last 12 months), with a 50% leaving guess`,
        }
      : { customers: 3680, yearlySpend: 320, share: 40, source: "made-up sample numbers" };

  return (
    <>
      <DataSourceBanner meta={meta} />
      <ModelNote model={meta.models.forecast} title="Revenue forecast" />

      <section aria-label="Revenue summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {latest ? `Last full month (${latest.month})` : "Last full month"}
          </p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{latest?.actual !== undefined ? <Money value={latest.actual} /> : "—"}</p>
          {monthChange !== null ? (
            <p className={monthChange >= 0 ? "text-xs font-medium text-emerald-700" : "text-xs font-medium text-rose-700"}>
              {formatSignedPercent(monthChange)} vs previous month
            </p>
          ) : (
            <p className="text-xs text-slate-500">Not enough history to compare</p>
          )}
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Next 3 months forecast</p>
          {forecast.length === 0 ? (
            <NotAvailableValue reason={reasonFor(meta, "revenueForecast")} />
          ) : (
            <>
              <p className="mt-2 text-2xl font-semibold tabular-nums"><Money value={forecastTotal} /></p>
              <p className="text-xs text-slate-500">{live ? "Model estimate (see range on the chart)" : "Includes holiday peak"}</p>
            </>
          )}
        </Card>
        {live ? (
          <>
            <Card className="p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">At-Risk + Lost revenue (12 mo)</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums text-rose-700"><Money value={totalAtRisk} /></p>
              <p className="text-xs text-slate-500">What these customers spent — historical, not a predicted loss</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Share of 12-month revenue</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums">{formatPercent(revenue12m ? (totalAtRisk / revenue12m) * 100 : 0)}</p>
              <p className="text-xs text-slate-500">of <Money value={revenue12m} /> in the last 12 months</p>
            </Card>
          </>
        ) : (
          <>
            <Card className="p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Revenue at risk (month)</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums text-rose-700"><Money value={currentAtRisk} /></p>
              <p className="text-xs text-slate-500">{formatPercent(latest?.actual ? (currentAtRisk / latest.actual) * 100 : 0)} of monthly revenue</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">12-month exposure</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums"><Money value={totalAtRisk} /></p>
              <p className="text-xs text-slate-500">Predicted loss if at-risk cohorts churn</p>
            </Card>
          </>
        )}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>{live && !forecastPredicted ? "Revenue trend" : "Revenue trend & forecast"}</CardTitle>
          <CardDescription>
            {!live
              ? "Actual revenue through October; forecast with confidence range for the next three months."
              : forecastPredicted
                ? "Monthly revenue from your orders, then a 3-month trend forecast (model estimate) with a shaded 80% range. The last actual month may be partial."
                : `Monthly revenue from your orders. The last month may be partial (month to date). Forecast not shown: ${reasonFor(meta, "revenueForecast") ?? "not available."}`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RevenueForecastChart data={series} />
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        {atRiskTrend ? (
          <Card>
            <CardHeader>
              <CardTitle>Revenue at risk trend</CardTitle>
              <CardDescription>Monthly revenue from customers predicted to churn.</CardDescription>
            </CardHeader>
            <CardContent>
              <RevenueAtRiskChart data={atRiskTrend} />
            </CardContent>
          </Card>
        ) : null}
        <Card className={atRiskTrend ? undefined : "xl:col-span-2"}>
          <CardHeader>
            <CardTitle>Revenue at risk by segment</CardTitle>
            <CardDescription>
              {live
                ? "Last-12-month spend of customers now At-Risk or Lost — where win-back effort protects the most revenue."
                : "Where retention spend protects the most revenue."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {atRiskBySegment.length === 0 ? (
              <EmptyState title="Not enough customers to segment" description="Segmentation needs at least 20 customers." />
            ) : (
              atRiskBySegment.map((item) => (
                <div key={item.segment}>
                  <div className="mb-1.5 flex justify-between gap-2 text-sm">
                    <span className="text-slate-700">{item.segment} · {item.customers} customers</span>
                    <span className="font-medium tabular-nums"><Money value={item.atRisk} /></span>
                  </div>
                  <Progress value={item.atRisk} max={totalAtRisk || 1} tone="critical" label={`${item.segment} revenue at risk`} />
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {drivers.map((group) => {
          const max = Math.max(1, ...group.rows.map((r) => r.revenue));
          return (
            <Card key={group.title} className={drivers.length === 1 ? "xl:col-span-2" : undefined}>
              <CardHeader>
                <CardTitle>{group.title}</CardTitle>
                <CardDescription>{live ? "Revenue and share of the total." : "Contribution to revenue over the last 12 months."}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {group.rows.length === 0 ? (
                  <p className="text-sm text-slate-500">No orders in this period.</p>
                ) : (
                  group.rows.slice(0, 8).map((item) => (
                    <div key={item.name}>
                      <div className="mb-1.5 flex justify-between gap-2 text-sm">
                        <span className="text-slate-700">{item.name}</span>
                        <span className="shrink-0 font-medium tabular-nums">
                          <Money value={item.revenue} /> · {formatPercent(item.share, 0)}
                        </span>
                      </div>
                      <Progress value={item.revenue} max={max} label={`${item.name} revenue`} />
                      {item.orders != null && item.customers != null ? (
                        <p className="mt-1 text-xs text-slate-500">
                          {formatNumber(item.orders)} orders · {formatNumber(item.customers)} customers
                          {item.avgOrderValue != null ? (
                            <>
                              {" "}· average order <Money value={item.avgOrderValue} />
                            </>
                          ) : null}
                          {item.repeatRate != null ? ` · ${formatPercent(item.repeatRate, 0)} bought again` : ""}
                        </p>
                      ) : null}
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Revenue at risk calculator</CardTitle>
          <CardDescription>
            Try a &ldquo;what if&rdquo;: how much yearly revenue is exposed if some of these customers leave? Runs in
            your browser from the sliders.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RevenueAtRiskCalculator key={calculatorDefaults.source} defaults={calculatorDefaults} />
        </CardContent>
      </Card>
    </>
  );
}
