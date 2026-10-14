import { DemoBanner } from "@/components/demo-banner";
import { PageHeader } from "@/components/page-header";
import { ClvBySegmentChart } from "@/components/charts/dashboard-charts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getClvOverview } from "@/lib/api/customer-intelligence";
import { formatCurrency, formatSignedPercent } from "@/lib/utils";

function growthLabel(growth: number) {
  if (growth >= 25) return { label: "High potential", variant: "success" as const };
  if (growth >= 0) return { label: "Moderate", variant: "info" as const };
  return { label: "Declining", variant: "danger" as const };
}

export default async function ClvPage() {
  const { averageClv, averagePredictedClv, segments, customers } = await getClvOverview();
  const portfolioGrowth = ((averagePredictedClv - averageClv) / averageClv) * 100;
  const rows = customers
    .map((c) => ({ ...c, growth: ((c.predictedClv - c.currentClv) / c.currentClv) * 100 }))
    .sort((a, b) => b.growth - a.growth);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Customer Lifetime Value"
        description="Forecast future customer value with current CLV, predicted CLV, and growth potential for every customer and segment."
      />
      <DemoBanner />

      <section aria-label="CLV summary" className="grid gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Average current CLV</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatCurrency(averageClv)}</p>
          <p className="text-xs text-slate-500">Weighted across all segments</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Average predicted CLV</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{formatCurrency(averagePredictedClv)}</p>
          <p className="text-xs text-slate-500">12-month forward forecast</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Portfolio growth potential</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums text-emerald-700">{formatSignedPercent(portfolioGrowth)}</p>
          <p className="text-xs text-slate-500">Predicted vs current CLV</p>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Current vs predicted CLV by segment</CardTitle>
          <CardDescription>
            Champions and Potential Loyalists are expanding; At-Risk and Lost customers are contracting.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ClvBySegmentChart data={segments} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Customer CLV forecast</CardTitle>
          <CardDescription>Sorted by growth potential. Negative growth flags customers to retain.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <caption className="sr-only">Current CLV, predicted CLV, and growth potential per customer</caption>
              <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="px-3 py-3 font-medium">Customer</th>
                  <th scope="col" className="px-3 py-3 font-medium">Segment</th>
                  <th scope="col" className="px-3 py-3 text-right font-medium">Current CLV</th>
                  <th scope="col" className="px-3 py-3 text-right font-medium">Predicted CLV</th>
                  <th scope="col" className="px-3 py-3 text-right font-medium">Change</th>
                  <th scope="col" className="px-3 py-3 font-medium">Growth potential</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const status = growthLabel(row.growth);
                  return (
                    <tr key={row.id} className="border-b border-slate-100 last:border-0">
                      <td className="px-3 py-3 font-medium text-slate-900">{row.name}</td>
                      <td className="px-3 py-3 text-slate-700">{row.segment}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{formatCurrency(row.currentClv)}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{formatCurrency(row.predictedClv)}</td>
                      <td
                        className={
                          row.growth >= 0
                            ? "px-3 py-3 text-right font-medium tabular-nums text-emerald-700"
                            : "px-3 py-3 text-right font-medium tabular-nums text-rose-700"
                        }
                      >
                        {formatSignedPercent(row.growth)}
                      </td>
                      <td className="px-3 py-3">
                        <Badge variant={status.variant}>{status.label}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}