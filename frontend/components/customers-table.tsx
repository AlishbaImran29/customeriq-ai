import { NotAvailableCell } from "@/components/not-available";
import { Badge, riskVariant } from "@/components/ui/badge";
import { Money } from "@/components/money";
import { formatDate, formatPercent } from "@/lib/utils";
import type { Customer } from "@/lib/types";

export function CustomersTable({
  rows,
  caption,
  riskLabel = "Churn risk",
}: {
  rows: Customer[];
  /** Visually hidden table description for screen readers. */
  caption: string;
  /** Column heading for `riskLevel` ("Inactivity" for live, rule-based data). */
  riskLabel?: string;
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
            <th scope="col" className="px-3 py-3 font-medium">{riskLabel}</th>
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
                  {row.id}
                  {row.channel ? ` · ${row.channel}` : ""}
                </p>
              </td>
              <td className="px-3 py-3 text-slate-700">
                {row.segment ?? <span className="text-slate-400">Not segmented</span>}
              </td>
              <td className="px-3 py-3 font-medium tabular-nums">{row.healthScore}</td>
              <td className="px-3 py-3 tabular-nums"><Money value={row.currentClv} /></td>
              <td className="px-3 py-3 tabular-nums">
                {row.predictedClv === null ? <NotAvailableCell /> : <Money value={row.predictedClv} />}
              </td>
              <td className="px-3 py-3">
                <div className="flex items-center gap-2">
                  <Badge variant={riskVariant(row.riskLevel)}>{row.riskLevel}</Badge>
                  <span className="text-xs tabular-nums text-slate-500">
                    {row.churnProbability !== null
                      ? formatPercent(row.churnProbability, 0)
                      : row.daysSinceLastOrder !== undefined
                        ? `${row.daysSinceLastOrder}d ago`
                        : null}
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
