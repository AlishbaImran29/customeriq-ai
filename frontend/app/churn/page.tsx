import { AlertTriangle, ShieldAlert, TrendingDown } from "lucide-react";
import { CustomerExplorer } from "@/components/customer-explorer";
import { DemoBanner } from "@/components/demo-banner";
import { PageHeader } from "@/components/page-header";
import { RiskDistributionChart } from "@/components/charts/dashboard-charts";
import { Badge, riskVariant } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { getChurnOverview } from "@/lib/api/customer-intelligence";
import { formatNumber, formatPercent } from "@/lib/utils";

export default async function ChurnPage() {
  const { churnRate, churnRateDelta, distribution, customers } = await getChurnOverview();
  const total = distribution.reduce((sum, b) => sum + b.customers, 0);
  const elevated = distribution
    .filter((b) => b.level === "High" || b.level === "Critical")
    .reduce((sum, b) => sum + b.customers, 0);
  const critical = distribution.find((b) => b.level === "Critical")?.customers ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Churn Prediction"
        description="Which customers are likely to stop purchasing, with churn probability, risk level, and a recommended action for each."
      />
      <DemoBanner />

      <section aria-label="Churn summary" className="grid gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            <TrendingDown className="h-4 w-4" aria-hidden="true" /> Predicted churn rate
          </p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatPercent(churnRate)}</p>
          <p className={churnRateDelta > 0 ? "text-xs font-medium text-rose-600" : "text-xs font-medium text-emerald-700"}>
            {churnRateDelta > 0 ? "+" : ""}
            {churnRateDelta.toFixed(1)} pts vs last period
          </p>
        </Card>
        <Card className="p-4">
          <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" /> High + critical risk
          </p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatNumber(elevated)}</p>
          <p className="text-xs text-slate-500">{formatPercent((elevated / total) * 100)} of customers</p>
        </Card>
        <Card className="p-4">
          <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            <ShieldAlert className="h-4 w-4" aria-hidden="true" /> Critical risk
          </p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatNumber(critical)}</p>
          <p className="text-xs text-slate-500">Churn probability of 80% or higher</p>
        </Card>
      </section>

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Risk distribution</CardTitle>
            <CardDescription>Customers by churn risk level.</CardDescription>
          </CardHeader>
          <CardContent>
            <RiskDistributionChart data={distribution} />
          </CardContent>
        </Card>
        <div className="grid gap-4 md:grid-cols-3 xl:col-span-3">
          {customers.slice(0, 3).map((customer) => (
            <Card key={customer.id} className="flex flex-col p-4">
              <p className="text-sm font-medium text-slate-900">{customer.name}</p>
              <p className="text-xs text-slate-500">{customer.segment}</p>
              <p className="mt-4 text-3xl font-semibold tabular-nums">{formatPercent(customer.churnProbability, 0)}</p>
              <p className="text-xs text-slate-500">churn probability</p>
              <Progress
                className="mt-2"
                value={customer.churnProbability}
                tone="critical"
                label={`${customer.name} churn probability`}
              />
              <div className="mt-3">
                <Badge variant={riskVariant(customer.riskLevel)}>{customer.riskLevel} risk</Badge>
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
          <CardTitle>Churn predictions</CardTitle>
          <CardDescription>Sorted by churn probability, highest first.</CardDescription>
        </CardHeader>
        <CardContent>
          <CustomerExplorer customers={customers} caption="Customers sorted by churn probability" />
        </CardContent>
      </Card>
    </div>
  );
}