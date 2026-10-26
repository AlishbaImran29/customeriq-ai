"use client";

import { useEffect, useState } from "react";
import { MessengerGate } from "@/components/messenger-bits";
import { Money } from "@/components/money";
import { ErrorState } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Skeleton } from "@/components/ui/skeleton";
import { getResults, type Comparison, type Group, type MessengerResults } from "@/lib/api/messaging";
import { eventLabel, percentText, pointsText } from "@/lib/messenger-text";
import { fmt } from "@/lib/format";

/**
 * What the messages did. Counts per template, campaign and journey, orders and revenue within 7 days, and the honest test:
 * customers who were messaged versus a holdout group who were not. Small groups show no verdict, and a gap that could be chance says so.
 */
export function MessengerResultsBoard() {
  return (
    <MessengerGate>
      <ResultsContent />
    </MessengerGate>
  );
}

function ResultsContent() {
  const [days, setDays] = useState(30);
  const [dry, setDry] = useState(false);
  const [data, setData] = useState<MessengerResults | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getResults(days, dry)
      .then((r) => !cancelled && (setData(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [days, dry]);

  if (failed) return <ErrorState title="Could not load the results" description="Please check your connection and reload the page." />;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-4">
        <FilterPills
          label="Period" value={String(days)} onChange={(v) => setDays(Number(v))}
          options={[{ value: "7", label: fmt("{n} days", { n: 7 }) }, { value: "30", label: fmt("{n} days", { n: 30 }) }, { value: "90", label: fmt("{n} days", { n: 90 }) }]}
        />
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input type="checkbox" checked={dry} onChange={(e) => setDry(e.target.checked)} className="h-4 w-4 accent-[var(--color-accent)]" />
          Include demo messages (dry run)
        </label>
      </div>
      {!data ? <Skeleton className="h-64 w-full" /> : (
        <>
          <Card>
            <CardHeader><CardTitle>Overall</CardTitle><CardDescription>Orders and revenue count only when the customer ordered within 7 days after a message.</CardDescription></CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <Stat label="Sent" value={data.totals.sent} /><Stat label="Delivered" value={data.totals.delivered} />
                <Stat label="Read" value={data.totals.read} /><Stat label="Replied" value={data.totals.replied} />
                <Stat label="Failed" value={data.totals.failed} /><Stat label="Not sent" value={data.totals.skipped} />
                <Stat label="Stopped by customers" value={data.totals.optOuts} /><Stat label="Orders after a message" value={data.totals.orders} />
              </dl>
              <p className="mt-3 text-sm text-ink-2">Revenue after a message: <Money value={data.totals.revenue} /></p>
              <p className="mt-1 text-xs text-muted">
                {data.cost.total === null
                  ? fmt("{u} order updates and {m} marketing messages. Add what each costs you in Settings to see the WhatsApp cost.", { u: data.cost.utilityMessages, m: data.cost.marketingMessages })
                  : <>WhatsApp cost: <Money value={data.cost.total} /></>}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Messaged vs not messaged</CardTitle><CardDescription>{fmt("A fair test needs at least {n} customers in each group.", { n: data.minGroupCount })}</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              {data.journeys.length === 0 ? <p className="text-sm text-muted">No journeys yet.</p> : data.journeys.map((j) => (
                <div key={j.journeyId} className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
                  <p className="font-medium text-ink">{j.name}{j.enabled ? "" : ` (${"off"})`}</p>
                  <ComparisonText c={j.comparison} />
                </div>
              ))}
            </CardContent>
          </Card>

          <GroupTable title="By campaign" rows={data.campaigns} />
          <GroupTable title="By template" rows={data.templates} label={(g) => eventLabel(g.name)} />
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return <div><dt className="text-xs text-muted">{label}</dt><dd className="text-lg font-semibold text-ink">{value}</dd></div>;
}

function ComparisonText({ c }: { c: Comparison }) {
  if (!c.enough) return <p className="text-ink-2">{fmt("Not enough customers yet to tell: {messaged} messaged and {holdout} held back, and each group needs {needed}.", { messaged: c.messaged, holdout: c.holdout, needed: c.needed })}</p>;
  return (
    <div className="space-y-1 text-ink-2">
      <p>{fmt("Messaged: {a} ordered again ({n} customers). Not messaged: {b} ({h} customers).", { a: percentText(c.messagedRate), n: c.messaged, b: percentText(c.holdoutRate), h: c.holdout })}</p>
      <p>
        {fmt("Difference: {d} points (95% range {lo} to {hi}).", { d: pointsText(c.difference), lo: pointsText(c.low), hi: pointsText(c.high) })}{" "}
        <strong className={c.couldBeChance ? "text-warning" : "text-success"}>{c.couldBeChance ? "This could be chance." : "This is unlikely to be chance."}</strong>
      </p>
    </div>
  );
}

function GroupTable({ title, rows, label }: { title: string; rows: Group[]; label?: (g: Group) => string }) {
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="overflow-x-auto">
        {rows.length === 0 ? <p className="text-sm text-muted">Nothing yet.</p> : (
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead className="text-xs text-muted">
              <tr><th className="py-1 pr-3 font-medium">Name</th><th className="px-2 font-medium">Sent</th><th className="px-2 font-medium">Read</th><th className="px-2 font-medium">Replied</th><th className="px-2 font-medium">Stopped</th><th className="px-2 font-medium">Orders</th><th className="px-2 font-medium">Revenue</th></tr>
            </thead>
            <tbody className="text-ink-2">
              {rows.map((g, i) => (
                <tr key={`${g.id ?? "x"}-${i}`} className="border-t border-line">
                  <td className="py-1.5 pr-3 text-ink">{label ? label(g) : g.name}</td><td className="px-2">{g.sent}</td><td className="px-2">{g.read}</td><td className="px-2">{g.replied}</td><td className="px-2">{g.optOuts}</td><td className="px-2">{g.orders}</td><td className="px-2"><Money value={g.revenue} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
