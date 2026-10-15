import { Suspense } from "react";
import { AlertTriangle, ShieldAlert, TrendingDown } from "lucide-react";
import { CustomerExplorer } from "@/components/customer-explorer";
import { DataErrorState, DataSourceBanner, NoDataState, PageSkeleton, load } from "@/components/data-state";
import { NotAvailableValue } from "@/components/not-available";
import { PageHeader } from "@/components/page-header";
import { RiskDistributionChart } from "@/components/charts/dashboard-charts";
import { Badge, riskVariant } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { getChurnOverview } from "@/lib/api/customer-intelligence";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";

export default function ChurnPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Churn Prediction"
        description="Which customers are likely to stop purchasing, with churn probability, risk level, and a recommended action for each."
      />
      <Suspense fallback={<PageSkeleton cards={3} />}>
        <ChurnContent />
      </Suspense>
    </div>
  );
}

async function ChurnContent() {
  const result = await load(getChurnOverview);
  if (!result.ok) return <DataErrorState error={result.error} />;
  const { meta, churnRate, churnRateDelta, distribution, customers } = result.data;
  if (meta.source === "live" && !meta.asOf) return <NoDataState />;
  const live = meta.source === "live";
  const total = distribution.reduce((sum, b) => sum + b.customers, 0);
  const elevated = distribution
    .filter((b) => b.level === "High" || b.level === "Critical")
    .reduce((sum, b) => sum + b.customers, 0);
  const critical = distribution.find((b) => b.level === "Critical")?.customers ?? 0;

  return (
    <>
      <DataSourceBanner meta={meta} />
      {live ? (
        <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600">
          <strong className="text-slate-900">Churn probability is not available yet.</strong> It needs a
          trained and validated model (Phase 4). Until then this page shows a <strong>rule-based inactivity
          level</strong>: days since a customer&apos;s last order divided by their usual gap between orders
          (Low ≤ 1×, Medium ≤ 1.5×, High ≤ 2.5×, Critical beyond). It describes behaviour; it does not
          predict it.
        </div>
      ) : null}

      <section aria-label="Churn summary" className="grid gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            <TrendingDown className="h-4 w-4" aria-hidden="true" /> Predicted churn rate
          </p>
          {churnRate === null ? (
            <NotAvailableValue />
          ) : (
            <>
              <p className="mt-2 text-2xl font-semibold tabular-nums">{formatPercent(churnRate)}</p>
              {churnRateDelta !== null ? (
                <p className={churnRateDelta > 0 ? "text-xs font-medium text-rose-600" : "text-xs font-medium text-emerald-700"}>
                  {churnRateDelta > 0 ? "+" : ""}
                  {churnRateDelta.toFixed(1)} pts vs last period
                </p>
              ) : null}
            </>
          )}
        </Card>
        <Card className="p-4">
          <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" /> {live ? "High + critical inactivity" : "High + critical risk"}
          </p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatNumber(elevated)}</p>
          <p className="text-xs text-slate-500">{formatPercent(total ? (elevated / total) * 100 : 0)} of customers</p>
        </Card>
        <Card className="p-4">
          <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            <ShieldAlert className="h-4 w-4" aria-hidden="true" /> {live ? "Critical inactivity" : "Critical risk"}
          </p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatNumber(critical)}</p>
          <p className="text-xs text-slate-500">
            {live ? "More than 2.5× their usual gap since the last order" : "Churn probability of 80% or higher"}
          </p>
        </Card>
      </section>

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>{live ? "Inactivity levels" : "Risk distribution"}</CardTitle>
            <CardDescription>{live ? "Customers by rule-based inactivity level." : "Customers by churn risk level."}</CardDescription>
          </CardHeader>
          <CardContent>
            <RiskDistributionChart data={distribution} />
          </CardContent>
        </Card>
        <div className="grid gap-4 md:grid-cols-3 xl:col-span-3">
          {customers.slice(0, 3).map((customer) => (
            <Card key={customer.id} className="flex flex-col p-4">
              <p className="text-sm font-medium text-slate-900">{customer.name}</p>
              <p className="text-xs text-slate-500">{customer.segment ?? "Not segmented"}</p>
              {customer.churnProbability !== null ? (
                <>
                  <p className="mt-4 text-3xl font-semibold tabular-nums">{formatPercent(customer.churnProbability, 0)}</p>
                  <p className="text-xs text-slate-500">churn probability</p>
                  <Progress className="mt-2" value={customer.churnProbability} tone="critical" label={`${customer.name} churn probability`} />
                </>
              ) : (
                <>
                  <p className="mt-4 text-3xl font-semibold tabular-nums">{customer.daysSinceLastOrder ?? "—"}</p>
                  <p className="text-xs text-slate-500">days since last order · {formatCurrency(customer.revenue)} spent</p>
                </>
              )}
              <div className="mt-3">
                <Badge variant={riskVariant(customer.riskLevel)}>
                  {customer.riskLevel} {live ? "inactivity" : "risk"}
                </Badge>
              </div>
              <p className="mt-auto pt-3 text-sm text-slate-600">
                <span className="font-medium text-slate-800">Action: </span>
                {customer.recommendedAction}
              </p>
            </Card>
          ))}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{live ? "Customers by inactivity" : "Churn predictions"}</CardTitle>
          <CardDescription>
            {live ? "Most inactive first, relative to each customer's own buying rhythm." : "Sorted by churn probability, highest first."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CustomerExplorer
            customers={customers}
            caption={live ? "Customers sorted by inactivity" : "Customers sorted by churn probability"}
            riskLabel={live ? "Inactivity" : "Churn risk"}
          />
        </CardContent>
      </Card>
    </>
  );
}
