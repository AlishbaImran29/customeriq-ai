"use client";

import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, Banknote, Clock, Download, FlaskConical, HandCoins, Hourglass, TriangleAlert, Truck } from "lucide-react";
import { KpiCard } from "@/components/kpi-card";
import { Money } from "@/components/money";
import { PaymentForm } from "@/components/payment-form";
import { PaymentUpload } from "@/components/payment-upload";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Skeleton } from "@/components/ui/skeleton";
import { CASH_AVAILABLE, getCashTracker, getPendingParcels, type CashTracker, type CourierCash } from "@/lib/api/cash";
import { getShipmentSummary } from "@/lib/api/shipments";
import { downloadCsv } from "@/lib/csv-export";
import { formatMoney } from "@/lib/currency";
import { formatNumber } from "@/lib/utils";
import { fmt } from "@/lib/format";

const THRESHOLDS = [7, 14, 21, 30];

/**
 * The Cash Tracker: COD money the couriers collected and have not handed over yet. Every figure is a sum
 * of recorded amounts (no model, no estimate). "Average days to pay" is a conclusion about a courier, so
 * it appears only with enough fully paid parcels; below that it says "Not enough data yet".
 */
export function CashTrackerBoard() {
  const format = (value: number) => formatMoney(value);
  const [alertDays, setAlertDays] = useState(14);
  const [data, setData] = useState<CashTracker | null>(null);
  const [couriers, setCouriers] = useState<string[]>([]);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!CASH_AVAILABLE) return;
    let cancelled = false;
    getCashTracker(alertDays)
      .then((d) => !cancelled && (setData(d), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [alertDays, version]);

  useEffect(() => {
    if (!CASH_AVAILABLE) return;
    getShipmentSummary().then((s) => setCouriers(s.couriers)).catch(() => undefined);
  }, []);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  async function exportPending() {
    setExporting(true);
    try {
      const rows = await getPendingParcels();
      downloadCsv(
        "pending-cod.csv",
        ["Courier", "City", "Order / shipment", "Delivered on", "Days pending", "COD amount (PKR)", "Paid so far (PKR)", "Still owed (PKR)", "Status"],
        rows.map((r) => [r.courier, r.city ?? "", r.reference, r.deliveredOn, r.daysPending, r.codAmount, r.paid, r.stillOwed, r.status === "partly_paid" ? "partly paid" : "pending"]),
      );
    } finally {
      setExporting(false);
    }
  }

  if (!CASH_AVAILABLE) {
    return (
      <EmptyState
        icon={Banknote}
        title="The Cash Tracker needs your own shipments"
        description="There is no sample data for this page, because made-up money figures would be misleading. Connect the backend and import your shipments to see it."
      />
    );
  }
  if (failed) return <ErrorState title="Could not load the Cash Tracker" description="Please check your connection and reload the page." />;
  if (!data) return <Skeleton className="h-64 w-full" />;

  const nothing = data.realCodParcels + data.demoCodParcels === 0;
  const maxBucket = Math.max(1, ...data.buckets.map((b) => b.amount));

  return (
    <div className="space-y-5">
      {data.sourceUsed === "demo" && !nothing ? (
        <div role="status" className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-ink">
          <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
          <p>
            <strong>Demo data (synthetic).</strong>{" "}
            These shipments and payments are made up to show how the page works. They are not real courier results.
          </p>
        </div>
      ) : null}

      {nothing ? (
        <EmptyState
          icon={Banknote}
          title="No delivered COD parcels yet"
          description="Import your courier shipments with the cash on delivery amount, then add the payments couriers send you."
        />
      ) : (
        <>
          <section aria-label="Cash summary" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard label="Total COD delivered" value={<Money value={data.deliveredCod} />} delta={null} note={fmt("{count} unpaid parcels", { count: formatNumber(data.unpaidParcels) })} icon={Banknote} />
            <KpiCard label="Received from couriers" value={<Money value={data.received} />} delta={null} note={fmt("{count} payments recorded", { count: formatNumber(data.payments) })} icon={BadgeCheck} />
            <KpiCard label="Pending with couriers" value={<Money value={data.pending} />} delta={null} note={data.credit > 0 ? fmt("{amount} paid in advance", { amount: format(data.credit) }) : undefined} icon={Hourglass} />
            <KpiCard label="Oldest pending" value={data.oldestPendingDays === null ? "None" : fmt("{days} days", { days: data.oldestPendingDays })} delta={null} note={fmt("Counted to {date}", { date: data.asOf })} icon={Clock} />
          </section>

          <Card>
            <CardContent className="space-y-3 pt-5">
              <FilterPills
                label="Alert after this many days unpaid"
                value={String(alertDays)}
                onChange={(v) => setAlertDays(Number(v))}
                options={THRESHOLDS.map((d) => ({ value: String(d), label: fmt("{days} days", { days: d }) }))}
              />
              {data.alerts.length === 0 ? (
                <p className="text-sm text-muted">{fmt("No courier owes money older than {days} days.", { days: alertDays })}</p>
              ) : (
                <ul className="space-y-2">
                  {data.alerts.map((c) => (
                    <li key={c.courier} role="note" className="flex items-start gap-3 rounded-xl border border-serious/40 bg-serious/10 px-4 py-3 text-sm text-ink">
                      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-serious" aria-hidden="true" />
                      <p>
                        {fmt("{courier} owes {amount} on {count} parcels delivered more than {days} days ago.", {
                          courier: c.courier, amount: format(c.overdueAmount), count: c.overdueParcels, days: alertDays,
                        })}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>How old is the unpaid money?</CardTitle>
              <CardDescription>Days since the parcel was delivered.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="grid gap-3 sm:grid-cols-3">
                {data.buckets.map((b) => (
                  <li key={b.label} className="rounded-xl border border-line bg-surface-2 p-3">
                    <p className="text-xs font-medium text-muted">{fmt("{range} days", { range: b.label })}</p>
                    <p className="mt-1 text-lg font-semibold text-ink"><Money value={b.amount} compact /></p>
                    <p className="text-xs text-muted">{fmt("{count} parcels", { count: formatNumber(b.parcels) })}</p>
                    <div className="mt-2 h-1.5 rounded-full bg-surface-3" aria-hidden="true">
                      <div className="h-1.5 rounded-full bg-accent" style={{ width: `${Math.round((b.amount / maxBucket) * 100)}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-3">
              <CardTitle>Each courier</CardTitle>
              <Button variant="secondary" onClick={exportPending} disabled={exporting || data.unpaidParcels === 0}>
                <Download className="h-4 w-4" aria-hidden="true" />
                Export pending list (CSV)
              </Button>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3 md:hidden">
                {data.couriers.map((c) => (
                  <li key={c.courier} className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
                    <p className="flex items-center gap-2 font-medium text-ink"><Truck className="h-4 w-4 text-accent" aria-hidden="true" />{c.courier}</p>
                    <p className="mt-1 text-ink-2">Pending: <Money value={c.pending} /> · {fmt("{count} unpaid parcels", { count: c.unpaidParcels })}</p>
                    <p className="text-ink-2"><DaysToPay c={c} /></p>
                  </li>
                ))}
              </ul>
              <div className="hidden md:block">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Each courier</caption>
                  <thead className="text-xs text-muted">
                    <tr className="border-b border-line">
                      <th scope="col" className="py-2 pr-3 font-medium">Courier name</th>
                      <th scope="col" className="py-2 pr-3 text-right font-medium">Pending</th>
                      <th scope="col" className="py-2 pr-3 text-right font-medium">Unpaid parcels</th>
                      <th scope="col" className="py-2 pr-3 text-right font-medium">Oldest pending</th>
                      <th scope="col" className="py-2 font-medium">Average days to pay</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.couriers.map((c) => (
                      <tr key={c.courier} className="border-b border-line/60">
                        <td className="py-2.5 pr-3 font-medium text-ink">{c.courier}</td>
                        <td className="py-2.5 pr-3 text-right tabular-nums"><Money value={c.pending} /></td>
                        <td className="py-2.5 pr-3 text-right tabular-nums">{formatNumber(c.unpaidParcels)}</td>
                        <td className="py-2.5 pr-3 text-right tabular-nums">{c.oldestPendingDays === null ? "-" : fmt("{days} days", { days: c.oldestPendingDays })}</td>
                        <td className="py-2.5 text-ink-2"><DaysToPay c={c} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><HandCoins className="h-4 w-4 text-accent" aria-hidden="true" />Add a payment</CardTitle>
            <CardDescription>Each payment pays the oldest delivered parcels first, unless you name the orders it was for.</CardDescription>
          </CardHeader>
          <CardContent><PaymentForm couriers={couriers} onSaved={reload} /></CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Courier payments</CardTitle>
          </CardHeader>
          <CardContent><PaymentUpload onChange={reload} /></CardContent>
        </Card>
      </div>
    </div>
  );
}

function DaysToPay({ c }: { c: CourierCash }) {
  if (c.averageDaysToPay !== null) return <>{fmt("{days} days", { days: c.averageDaysToPay })}</>;
  return <span className="text-muted">Not enough data yet {fmt("({finished} paid, {needed} more needed)", { finished: c.paidParcels, needed: c.needed })}</span>;
}
