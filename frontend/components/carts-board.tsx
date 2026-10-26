"use client";

import { useEffect, useState } from "react";
import { MessengerGate, formatWhen } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Skeleton } from "@/components/ui/skeleton";
import { apiGet } from "@/lib/api/config";
import { percentText } from "@/lib/messenger-text";
import { fmt } from "@/lib/format";

type Cart = { id: number; customerName: string | null; items: string | null; total: number | null; currency: string | null; status: string; remindersSent: number; lastReminderAt: string | null; checkoutUpdatedAt: string; recoveredAt: string | null };
type Summary = { counts: Record<string, number>; reminded: number; recoveredAfterReminder: number; recoveryRate: number | null; minGroupCount: number; note: string };
const LABEL: Record<string, string> = { open: "Waiting", recovered: "Bought", expired: "Expired", no_contact: "Not messaged" };

/** Shoppers who left a Shopify checkout. Reminders go only to customers who agreed to be messaged; a purchase stops them at once. */
export function CartsBoard() {
  return (
    <MessengerGate>
      <CartsContent />
    </MessengerGate>
  );
}

function CartsContent() {
  const [show, setShow] = useState("all");
  const [carts, setCarts] = useState<Cart[] | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([apiGet<Cart[]>(`/api/v1/carts${show === "all" ? "" : `?status=${show}`}`), apiGet<Summary>("/api/v1/carts/summary")])
      .then(([c, s]) => !cancelled && (setCarts(c), setSummary(s), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [show]);

  if (failed) return <ErrorState title="Could not load the carts" description="Please check your connection and reload the page." />;
  return (
    <div className="space-y-5">
      {summary ? (
        <Card>
          <CardHeader><CardTitle>Overview</CardTitle><CardDescription>{summary.note}</CardDescription></CardHeader>
          <CardContent className="space-y-1 text-sm text-ink-2">
            <p>{fmt("{open} waiting, {recovered} bought, {expired} expired, {none} not messaged", { open: summary.counts.open, recovered: summary.counts.recovered, expired: summary.counts.expired, none: summary.counts.no_contact })}</p>
            <p>{summary.recoveryRate === null ? fmt("Not enough data yet: {n} reminded so far, {min} needed to show a rate.", { n: summary.reminded, min: summary.minGroupCount }) : fmt("{rate} of reminded shoppers bought ({n} of {total}).", { rate: percentText(summary.recoveryRate), n: summary.recoveredAfterReminder, total: summary.reminded })}</p>
          </CardContent>
        </Card>
      ) : <Skeleton className="h-24 w-full" />}
      <FilterPills label="Filter by status" value={show} onChange={setShow}
        options={[{ value: "all", label: "All" }, ...Object.keys(LABEL).map((k) => ({ value: k, label: LABEL[k] }))]} />
      {!carts ? <Skeleton className="h-40 w-full" /> : carts.length === 0 ? <p className="text-sm text-muted">No abandoned carts yet. Connect Shopify checkout events (see the setup notes) and approve the cart reminder templates.</p> : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {carts.map((c) => (
            <li key={c.id}>
              <Card className="h-full"><CardContent className="space-y-1 pt-5 text-sm">
                <p className="font-medium text-ink">{c.customerName ?? "Unknown shopper"} · {(LABEL[c.status] ?? c.status)}</p>
                <p className="text-ink-2">{c.items ?? "-"}{c.total !== null ? ` · ${c.currency ?? ""} ${c.total}` : ""}</p>
                <p className="text-xs text-muted">{formatWhen(c.checkoutUpdatedAt)} · {fmt("{n} reminders sent", { n: c.remindersSent })}</p>
              </CardContent></Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
