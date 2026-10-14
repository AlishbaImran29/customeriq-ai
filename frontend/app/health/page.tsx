import { Activity, CalendarClock, MousePointerClick, ShoppingBag } from "lucide-react";
import { DemoBanner } from "@/components/demo-banner";
import { PageHeader } from "@/components/page-header";
import { HealthDistributionChart } from "@/components/charts/dashboard-charts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, scoreTone } from "@/components/ui/progress";
import { getHealthOverview } from "@/lib/api/customer-intelligence";
import type { HealthFactors } from "@/lib/types";
import { formatNumber } from "@/lib/utils";

const factors: { key: keyof HealthFactors; label: string; description: string; icon: typeof Activity }[] = [
  { key: "purchaseFrequency", label: "Purchase frequency", description: "Orders per active month", icon: ShoppingBag },
  { key: "spendingBehavior", label: "Spending behavior", description: "Average order value and total spend", icon: Activity },
  { key: "engagement", label: "Customer engagement", description: "Email, site, and app interactions", icon: MousePointerClick },
  { key: "activityTrend", label: "Activity trend", description: "Recent activity vs the customer's baseline", icon: CalendarClock },
];

export default async function HealthPage() {
  const { weights, distribution, customers } = await getHealthOverview();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Customer Health Score"
        description="A 0–100 score combining purchase frequency, spending behavior, customer engagement, and activity trends."
      />
      <DemoBanner />

      <Card>
        <CardHeader>
          <CardTitle>How the score is calculated</CardTitle>
          <CardDescription>Each factor is normalised to 0–100 and weighted.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {factors.map((factor) => (
              <li key={factor.key} className="rounded-xl border border-slate-100 p-3">
                <div className="flex items-center justify-between gap-2">
                  <factor.icon className="h-4 w-4 text-teal-600" aria-hidden="true" />
                  <span className="text-lg font-semibold tabular-nums">{Math.round(weights[factor.key] * 100)}%</span>
                </div>
                <p className="mt-2 text-sm font-medium text-slate-900">{factor.label}</p>
                <p className="text-xs text-slate-500">{factor.description}</p>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Health distribution</CardTitle>
            <CardDescription>Customers in each health band.</CardDescription>
          </CardHeader>
          <CardContent>
            <HealthDistributionChart data={distribution} />
          </CardContent>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Bands</CardTitle>
            <CardDescription>Score ranges and customer counts.</CardDescription>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <caption className="sr-only">Customers per health band</caption>
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr className="border-b border-slate-200">
                  <th scope="col" className="py-2 text-left font-medium">Band</th>
                  <th scope="col" className="py-2 text-left font-medium">Score</th>
                  <th scope="col" className="py-2 text-right font-medium">Customers</th>
                </tr>
              </thead>
              <tbody>
                {distribution.map((bucket) => (
                  <tr key={bucket.label} className="border-b border-slate-100 last:border-0">
                    <td className="py-2.5 font-medium text-slate-900">{bucket.label}</td>
                    <td className="py-2.5 text-slate-600">{bucket.range}</td>
                    <td className="py-2.5 text-right tabular-nums">{formatNumber(bucket.customers)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Health drivers by customer</CardTitle>
          <CardDescription>Lowest scores first, so the customers needing attention appear at the top.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[880px] text-left text-sm">
              <caption className="sr-only">Health score and factor breakdown per customer</caption>
              <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="px-3 py-3 font-medium">Customer</th>
                  <th scope="col" className="px-3 py-3 font-medium">Health</th>
                  {factors.map((f) => (
                    <th key={f.key} scope="col" className="px-3 py-3 font-medium">{f.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {customers.map((row) => (
                  <tr key={row.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-3 py-3">
                      <p className="font-medium text-slate-900">{row.name}</p>
                      <p className="text-xs text-slate-500">{row.segment}</p>
                    </td>
                    <td className="px-3 py-3 text-lg font-semibold tabular-nums">{row.healthScore}</td>
                    {factors.map((f) => (
                      <td key={f.key} className="px-3 py-3">
                        <div className="flex items-center gap-2">
                          <Progress
                            value={row.healthFactors[f.key]}
                            tone={scoreTone(row.healthFactors[f.key])}
                            label={`${row.name} ${f.label}`}
                            className="w-20"
                          />
                          <span className="w-7 text-xs tabular-nums text-slate-600">{row.healthFactors[f.key]}</span>
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}