"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";
import { Money } from "@/components/money";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { API_MODE, ApiError } from "@/lib/api/config";
import { addAdSpend, deleteAdSpend, getCostSettings, getProfit, listAdSpend, saveCostSettings, type AdSpendRow, type GroupBy, type ProfitSummary } from "@/lib/api/profit";
import { percentText } from "@/lib/messenger-text";
import { fmt } from "@/lib/format";

const field = "flex flex-col gap-1 text-sm font-medium text-ink-2";
const GROUPS: GroupBy[] = ["product", "channel", "city", "courier", "customer"];
const GROUP_LABEL: Record<GroupBy, string> = { product: "By product", channel: "By channel", city: "By city", courier: "By courier", customer: "Top customers" };
const MISSING_TEXT: Record<string, string> = {
  product_cost: "orders left out because the product cost is unknown (add the item and its cost in Inventory)",
  packing: "orders counted without a packing cost (set it below)",
  courier_fee: "orders counted without a courier fee on record",
  return_shipping: "returned orders counted without a return shipping cost (set it below)",
};
const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Gross revenue vs delivered revenue vs profit, with every missing cost named. Profit is an estimate and the page says so. */
export function ProfitBoard() {
  if (API_MODE !== "live") return <p className="text-sm text-muted">Profit figures are built from your database. Connect the backend to see them.</p>;
  return <ProfitContent />;
}

function ProfitContent() {
  const [days, setDays] = useState("30");
  const [data, setData] = useState<ProfitSummary | null>(null);
  const [failed, setFailed] = useState(false);
  const [group, setGroup] = useState<GroupBy>("product");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const end = new Date();
    const start = new Date(end.getTime() - (Number(days) - 1) * 86_400_000);
    getProfit(iso(start), iso(end))
      .then((r) => !cancelled && (setData(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [days, version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (failed) return <ErrorState title="Could not load the profit figures" description="Please check your connection and reload the page." />;
  if (!data) return <Skeleton className="h-64 w-full" />;
  const missing = Object.entries(data.missing).filter(([, n]) => n > 0);
  return (
    <div className="space-y-5">
      <FilterPills label="Period" value={days} onChange={setDays} options={[{ value: "7", label: fmt("{n} days", { n: 7 }) }, { value: "30", label: fmt("{n} days", { n: 30 }) }, { value: "90", label: fmt("{n} days", { n: 90 }) }]} />

      <Card>
        <CardHeader><CardTitle>Four different money numbers</CardTitle><CardDescription>{data.note}</CardDescription></CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-3 text-sm lg:grid-cols-4">
            <Stat label="Gross order revenue" hint="Every order placed"><Money value={data.money.grossRevenue} /></Stat>
            <Stat label="Delivered revenue" hint="Delivered and not returned"><Money value={data.money.deliveredRevenue} /></Stat>
            <Stat label="Prepaid cash collected" hint="COD cash is on the Cash Tracker"><Money value={data.money.prepaidCollected} /></Stat>
            <Stat label="Estimated profit" hint="After every cost below">{data.money.estimatedProfit === null ? "Not available yet" : <Money value={data.money.estimatedProfit} />}</Stat>
          </dl>
          <p className="mt-3 text-xs text-muted">{fmt("{placed} orders placed, {ended} finished, {pending} still on the way. Profit counts {counted} orders; {unknown} are left out.", { placed: data.orders.placed, ended: data.orders.ended, pending: data.orders.pending, counted: data.orders.counted, unknown: data.orders.costUnknown })}</p>
        </CardContent>
      </Card>

      {missing.length > 0 ? (
        <p role="status" className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm text-ink">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
          <span>{missing.map(([k, n]) => `${n} ${(MISSING_TEXT[k] ?? k)}`).join("; ")}.</span>
        </p>
      ) : null}

      <Card>
        <CardHeader><CardTitle>Rates</CardTitle><CardDescription>{fmt("Shown only when there are at least {n} orders behind them.", { n: data.minGroupCount })}</CardDescription></CardHeader>
        <CardContent className="grid grid-cols-2 gap-3 text-sm lg:grid-cols-4">
          <Stat label="Return rate">{data.rates.returnRate === null ? "Not enough data yet" : percentText(data.rates.returnRate)}</Stat>
          <Stat label="Failed delivery rate">{data.rates.failedDeliveryRate === null ? "Not enough data yet" : percentText(data.rates.failedDeliveryRate)}</Stat>
          <Stat label="Repeat purchase rate">{data.rates.repeatPurchaseRate === null ? "Not enough data yet" : percentText(data.rates.repeatPurchaseRate)}</Stat>
          <Stat label="Items low in stock">{data.lowStockItems}</Stat>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Where the profit comes from</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <FilterPills label="Group by" value={group} onChange={setGroup} options={GROUPS.map((g) => ({ value: g, label: GROUP_LABEL[g] }))} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="text-xs text-muted"><tr><th className="py-1 pr-3 font-medium">Name</th><th className="px-2 font-medium">Orders</th><th className="px-2 font-medium">Revenue</th><th className="px-2 font-medium">Profit</th><th className="px-2 font-medium">Profit per order</th><th className="px-2 font-medium">Return rate</th></tr></thead>
              <tbody className="text-ink-2">
                {data.groups[group].length === 0 ? <tr><td className="py-2 text-muted" colSpan={6}>Nothing yet.</td></tr> : data.groups[group].map((g) => (
                  <tr key={g.key} className="border-t border-line">
                    <td className="py-1.5 pr-3 text-ink">{g.key}</td><td className="px-2">{g.orders}</td><td className="px-2"><Money value={g.revenue} /></td><td className="px-2"><Money value={g.profit} /></td>
                    <td className="px-2">{g.profitPerOrder === null ? <span className="text-xs text-muted">Not enough data yet</span> : <Money value={g.profitPerOrder} />}</td>
                    <td className="px-2">{g.returnRate === null ? "-" : percentText(g.returnRate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <CostsAndSpend onChanged={reload} />

      <Card>
        <CardHeader><CardTitle>How every number is worked out</CardTitle></CardHeader>
        <CardContent><dl className="space-y-2 text-sm">{data.definitions.map((d) => <div key={d.name}><dt className="font-medium text-ink">{d.name}</dt><dd className="text-ink-2">{d.formula}</dd></div>)}</dl></CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <div><dt className="text-xs text-muted">{label}</dt><dd className="text-lg font-semibold text-ink">{children}</dd>{hint ? <p className="text-[11px] text-muted">{hint}</p> : null}</div>;
}

function CostsAndSpend({ onChanged }: { onChanged: () => void }) {
  const [packing, setPacking] = useState("");
  const [ret, setRet] = useState("");
  const [rows, setRows] = useState<AdSpendRow[]>([]);
  const [day, setDay] = useState(iso(new Date()));
  const [channel, setChannel] = useState("instagram");
  const [amount, setAmount] = useState("");
  const [campaign, setCampaign] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    getCostSettings().then((s) => { setPacking(s.packingCost === null ? "" : String(s.packingCost)); setRet(s.returnShippingCost === null ? "" : String(s.returnShippingCost)); }).catch(() => undefined);
  }, []);
  useEffect(() => {
    listAdSpend().then(setRows).catch(() => undefined);
  }, [version]);

  const run = async (work: () => Promise<unknown>, done?: string) => {
    setNote(null);
    try {
      await work();
      if (done) setNote(done);
      setVersion((v) => v + 1);
      onChanged();
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    }
  };

  return (
    <Card>
      <CardHeader><CardTitle>Your costs and ad spend</CardTitle><CardDescription>Only numbers you type are used. Nothing is guessed.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3 sm:items-end">
          <label className={field}>Packing cost per order<Input value={packing} onChange={(e) => setPacking(e.target.value)} inputMode="decimal" /></label>
          <label className={field}>Return shipping cost<Input value={ret} onChange={(e) => setRet(e.target.value)} inputMode="decimal" /></label>
          <Button variant="secondary" onClick={() => run(() => saveCostSettings({ packingCost: packing === "" ? null : Number(packing), returnShippingCost: ret === "" ? null : Number(ret) }), "Saved.")}>Save costs (owner)</Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_1fr_1.4fr_auto] sm:items-end">
          <label className={field}>Day<Input type="date" value={day} onChange={(e) => setDay(e.target.value)} /></label>
          <label className={field}>Channel<Select value={channel} onChange={(e) => setChannel(e.target.value)} className="w-full">{["instagram", "facebook", "whatsapp", "website", "other"].map((c) => <option key={c} value={c}>{c}</option>)}</Select></label>
          <label className={field}>Ad spend<Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" /></label>
          <label className={field}>Campaign (optional)<Input value={campaign} onChange={(e) => setCampaign(e.target.value)} maxLength={160} /></label>
          <Button disabled={!amount || Number(amount) < 0} onClick={() => run(async () => { await addAdSpend({ spendDate: day, channel, amount: Number(amount), campaign: campaign || undefined }); setAmount(""); setCampaign(""); })}>Add</Button>
        </div>
        <div aria-live="polite">{note ? <p className="text-sm text-ink-2">{note}</p> : null}</div>
        <ul className="space-y-1 text-sm text-ink-2">
          {rows.slice(0, 15).map((r) => (
            <li key={r.id} className="flex items-center gap-2">{r.spendDate} · {r.channel}{r.campaign ? ` · ${r.campaign}` : ""} · <Money value={r.amount} />
              <Button variant="ghost" className="ml-auto !px-2 !py-1" aria-label="Delete" onClick={() => run(() => deleteAdSpend(r.id))}><Trash2 className="h-3.5 w-3.5" aria-hidden="true" /></Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
