import { DemoBanner } from "@/components/demo-banner";
import { PageHeader } from "@/components/page-header";
import { RevenueAtRiskCalculator } from "@/components/revenue-at-risk-calculator";
import { RevenueAtRiskChart, RevenueForecastChart } from "@/components/charts/dashboard-charts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { getRevenueOverview } from "@/lib/api/customer-intelligence";
import { formatCurrency, formatPercent, formatSignedPercent } from "@/lib/utils";

export default async function RevenuePage() {
  const { series, atRiskTrend, atRiskBySegment, drivers } = await getRevenueOverview();
  const actuals = series.filter((p) => p.actual !== undefined);
  const latest = actuals[actuals.length - 1]?.actual ?? 0;
  const previous = actuals[actuals.length - 2]?.actual ?? latest;
  const forecastTotal = series
    .filter((p) => p.actual === undefined && p.forecast !== undefined)
    .reduce((sum, p) => sum + (p.forecast ?? 0), 0);
  const currentAtRisk = atRiskTrend[atRiskTrend.length - 1]?.atRisk ?? 0;
  const totalAtRiskBySegment = atRiskBySegment.reduce((sum, s) => sum + s.atRisk, 0);
  const maxDriver = Math.max(...drivers.map((d) => d.impact));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Revenue Intelligence"
        description="Revenue trends, forecasting, revenue drivers, and revenue-at-risk analysis for growth decisions."
      />
      <DemoBanner />

      <section aria-label="Revenue summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">This month</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatCurrency(latest)}</p>
          <p className="text-xs font-medium text-emerald-700">
            {formatSignedPercent(((latest - previous) / previous) * 100)} vs last month
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Next 3 months forecast</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatCurrency(forecastTotal)}</p>
          <p className="text-xs text-slate-500">Includes holiday peak</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Revenue at risk (month)</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums text-rose-700">{formatCurrency(currentAtRisk)}</p>
          <p className="text-xs text-slate-500">{formatPercent((currentAtRisk / latest) * 100)} of monthly revenue</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">12-month exposure</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatCurrency(totalAtRiskBySegment)}</p>
          <p className="text-xs text-slate-500">Predicted loss if at-risk cohorts churn</p>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Revenue trend & forecast</CardTitle>
          <CardDescription>Actual revenue through October; forecast with confidence range for the next three months.</CardDescription>
        </CardHeader>
        <CardContent>
          <RevenueForecastChart data={series} />
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Revenue at risk trend</CardTitle>
            <CardDescription>Monthly revenue from customers predicted to churn.</CardDescription>
          </CardHeader>
          <CardContent>
            <RevenueAtRiskChart data={atRiskTrend} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Revenue at risk by segment</CardTitle>
            <CardDescription>Where retention spend protects the most revenue.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {atRiskBySegment.map((item) => (
              <div key={item.segment}>
                <div className="mb-1.5 flex justify-between gap-2 text-sm">
                  <span className="text-slate-700">{item.segment}</span>
                  <span className="font-medium tabular-nums">{formatCurrency(item.atRisk)}</span>
                </div>
                <Progress
                  value={item.atRisk}
                  max={totalAtRiskBySegment}
                  tone="critical"
                  label={`${item.segment} revenue at risk`}
                />
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Revenue drivers</CardTitle>
          <CardDescription>Contribution to revenue over the last 12 months.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {drivers.map((item) => (
            <div key={item.driver}>
              <div className="mb-1.5 flex justify-between gap-2 text-sm">
                <span className="text-slate-700">{item.driver}</span>
                <span className="shrink-0 font-medium tabular-nums">
                  {formatCurrency(item.impact)} · {formatPercent(item.share, 0)}
                </span>
              </div>
              <Progress value={item.impact} max={maxDriver} label={`${item.driver} revenue contribution`} />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Revenue at risk calculator</CardTitle>
          <CardDescription>Estimate exposure for a scenario. Calculated in your browser from the inputs below.</CardDescription>
        </CardHeader>
        <CardContent>
          <RevenueAtRiskCalculator />
        </CardContent>
      </Card>
    </div>
  );
}