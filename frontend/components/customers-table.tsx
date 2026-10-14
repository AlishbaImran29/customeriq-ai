import { Badge, riskVariant } from "@/components/ui/badge";
import { formatCurrency, formatDate, formatPercent } from "@/lib/utils";
import type { Customer } from "@/lib/types";

export function CustomersTable({
  rows,
  caption,
}: {
  rows: Customer[];
  /** Visually hidden table description for screen readers. */
  caption: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="px-3 py-3 font-medium">Customer</th>
            <th scope="col" className="px-3 py-3 font-medium">Segment</th>
            <th scope="col" className="px-3 py-3 font-medium">Health</th>
            <th scope="col" className="px-3 py-3 font-medium">CLV</th>
            <th scope="col" className="px-3 py-3 font-medium">Predicted CLV</th>
            <th scope="col" className="px-3 py-3 font-medium">Churn risk</th>
            <th scope="col" className="px-3 py-3 font-medium">Last purchase</th>
            <th scope="col" className="px-3 py-3 font-medium">Recommended action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60">
              <td className="px-3 py-3">
                <p className="font-medium text-slate-900">{row.name}</p>
                <p className="text-xs text-slate-500">
                  {row.id} · {row.store}
                </p>
              </td>
              <td className="px-3 py-3 text-slate-700">{row.segment}</td>
              <td className="px-3 py-3 font-medium tabular-nums">{row.healthScore}</td>
              <td className="px-3 py-3 tabular-nums">{formatCurrency(row.currentClv)}</td>
              <td className="px-3 py-3 tabular-nums">{formatCurrency(row.predictedClv)}</td>
              <td className="px-3 py-3">
                <div className="flex items-center gap-2">
                  <Badge variant={riskVariant(row.riskLevel)}>{row.riskLevel}</Badge>
                  <span className="text-xs tabular-nums text-slate-500">
                    {formatPercent(row.churnProbability, 0)}
                  </span>
                </div>
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-slate-600">
                {formatDate(row.lastPurchase)}
              </td>
              <td className="max-w-xs px-3 py-3 text-slate-600">{row.recommendedAction}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}