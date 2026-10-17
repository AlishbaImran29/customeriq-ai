import { Suspense } from "react";
import { Grid3x3 } from "lucide-react";
import { DataErrorState, DataSourceBanner, NoDataState, PageSkeleton, load } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getCohorts } from "@/lib/api/customer-intelligence";
import { cn, formatNumber } from "@/lib/utils";

export default function CohortsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Cohort Retention"
        description="Customers grouped by the month of their first order, and the share of each group that ordered again in the months after."
      />
      <Suspense fallback={<PageSkeleton cards={2} />}>
        <CohortsContent />
      </Suspense>
    </div>
  );
}

/** Teal that gets darker as retention rises; the number is always printed too. */
function cellStyle(value: number | null) {
  if (value === null) return undefined;
  return { backgroundColor: `rgba(34, 211, 238, ${(0.08 + (Math.min(value, 100) / 100) * 0.8).toFixed(2)})` };
}

async function CohortsContent() {
  const result = await load(getCohorts);
  if (!result.ok) return <DataErrorState error={result.error} />;
  const { meta, cohorts, averages, months, partialMonth } = result.data;
  if (meta.source === "demo") {
    return (
      <EmptyState
        icon={Grid3x3}
        title="Cohort retention needs your own orders"
        description="There is no sample data for this page, because made-up retention numbers would be misleading. Connect the backend and import your orders to see it."
      />
    );
  }
  if (!meta.asOf) return <NoDataState />;

  const offsets = Array.from({ length: months + 1 }, (_, i) => i);
  const month1 = averages[1];
  const month3 = averages[3];
  const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${v.toFixed(0)}%`);

  return (
    <>
      <DataSourceBanner meta={meta} />

      <section aria-label="Average retention" className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Average month 1 retention</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{pct(month1)}</p>
          <p className="text-xs text-muted">Customers who ordered again in the month after their first order.</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Average month 3 retention</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{pct(month3)}</p>
          <p className="text-xs text-muted">Customers who ordered in the third month after their first order.</p>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Retention by first-order month</CardTitle>
          <CardDescription>
            Month 0 is the first-order month (always 100%). Each later cell is the share of that group who placed an
            order in that month. The latest {cohorts.length} cohorts are shown.
            {partialMonth ? ` ${partialMonth} is still in progress, so it is not compared.` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[820px] border-separate border-spacing-0.5 text-center text-xs">
              <caption className="sr-only">Cohort retention: percent of each first-order-month group that ordered in each later month</caption>
              <thead className="text-muted">
                <tr>
                  <th scope="col" className="px-2 py-2 text-left font-medium">First order</th>
                  <th scope="col" className="px-2 py-2 text-right font-medium">Customers</th>
                  {offsets.map((m) => (
                    <th key={m} scope="col" className="px-1 py-2 font-medium">M{m}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cohorts.map((row) => (
                  <tr key={row.label}>
                    <th scope="row" className="whitespace-nowrap px-2 py-1.5 text-left font-medium text-ink">{row.label}</th>
                    <td className={cn("px-2 py-1.5 text-right tabular-nums", row.size < 20 ? "italic text-faint" : "text-ink-2")}>
                      {formatNumber(row.size)}
                    </td>
                    {row.retention.map((value, i) => (
                      <td
                        key={i}
                        style={cellStyle(value)}
                        className={cn(
                          "rounded px-1 py-1.5 tabular-nums",
                          value === null ? "text-faint" : value >= 55 ? "text-accent-ink" : "text-ink",
                        )}
                      >
                        {pct(value)}
                      </td>
                    ))}
                  </tr>
                ))}
                <tr className="border-t border-line">
                  <th scope="row" className="px-2 py-2 text-left font-semibold text-ink">Average</th>
                  <td />
                  {averages.map((value, i) => (
                    <td key={i} className="px-1 py-2 font-semibold tabular-nums text-ink">{pct(value)}</td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-muted">
            Averages weight each cohort by its size. Cohorts under 20 customers (shown in grey italics) swing a lot, so
            read them with care.
          </p>
        </CardContent>
      </Card>
    </>
  );
}
