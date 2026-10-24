"use client";

import { useEffect, useRef, useState } from "react";
import { Banknote, Calculator, Info, OctagonAlert, Save, Target, TriangleAlert, Wallet } from "lucide-react";
import { KpiCard } from "@/components/kpi-card";
import { LaunchStepFrame } from "@/components/launch-step-frame";
import { Money } from "@/components/money";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { calculateProfit, getProfitDefaults, saveProfit, type ProfitDefaults, type ProfitInput, type ProfitResult } from "@/lib/api/launch-steps";
import { ApiError } from "@/lib/api/config";
import type { Project } from "@/lib/api/launch";
import { useLanguage } from "@/lib/i18n";
import { formatNumber, formatPercent } from "@/lib/utils";

const field = "space-y-1 text-xs font-medium text-muted";

const WARNINGS: Record<string, { text: string; icon: typeof Info; className: string }> = {
  loss_per_order: { text: "You lose money on every order placed, before any ad cost. Raise the price, lower the cost, or expect fewer returns.", icon: OctagonAlert, className: "border-danger/40 bg-danger/10" },
  loss_when_delivered: { text: "Even a delivered order loses money at this price.", icon: OctagonAlert, className: "border-danger/40 bg-danger/10" },
  thin_margin: { text: "The profit is under 10% of the price. A few more returns or a small rise in ad cost could turn it into a loss.", icon: TriangleAlert, className: "border-warning/40 bg-warning/10" },
  no_budget: { text: "No ad budget was entered, so the number of orders needed to recover it is not shown.", icon: Info, className: "border-line bg-surface-2" },
};

const toNumber = (text: string) => (text.trim() === "" ? NaN : Number(text.replace(/,/g, "")));

/**
 * Step 5. Plain arithmetic on the seller's own numbers (all formulas are in backend/app/services/profit.py).
 * The answer is an ESTIMATE and is labelled so; the expected return rate matters most, which is why the
 * shop's real rate is offered only when enough orders of known outcome exist.
 */
export function ProfitCheckBoard() {
  return <LaunchStepFrame step={5}>{(project) => <ProfitStep key={project.id} project={project} />}</LaunchStepFrame>;
}

function ProfitStep({ project }: { project: Project }) {
  const { t, tf } = useLanguage();
  const [defaults, setDefaults] = useState<ProfitDefaults | null>(null);
  const [cost, setCost] = useState("");
  const [price, setPrice] = useState("");
  const [packing, setPacking] = useState("0");
  const [courier, setCourier] = useState("");
  const [returnShipping, setReturnShipping] = useState("");
  const [rate, setRate] = useState("");
  const [budget, setBudget] = useState("");
  const [computed, setComputed] = useState<ProfitResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const filled = useRef(false);

  useEffect(() => {
    let cancelled = false;
    getProfitDefaults(project.id).then((d) => {
      if (cancelled) return;
      setDefaults(d);
      if (filled.current) return;
      filled.current = true;
      if (d.saved) {
        setCost(String(d.saved.cost)); setPrice(String(d.saved.price)); setPacking(String(d.saved.packing)); setCourier(String(d.saved.courierFee));
        setReturnShipping(String(d.saved.returnShipping)); setRate(String(Math.round(d.saved.returnRate * 1000) / 10)); setBudget(String(d.saved.adBudget));
      } else {
        if (d.cost !== null) setCost(String(d.cost));
        if (d.returnRate !== null) setRate(String(Math.round(d.returnRate * 1000) / 10));
      }
    }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [project.id]);

  const numbers = {
    cost: toNumber(cost), price: toNumber(price), packing: toNumber(packing), courierFee: toNumber(courier),
    returnShipping: toNumber(returnShipping), returnRate: toNumber(rate) / 100, adBudget: budget.trim() === "" ? 0 : toNumber(budget),
  };
  const complete = Object.values(numbers).every((v) => Number.isFinite(v));
  const result = complete ? computed : null;        // incomplete numbers show no result
  const key = JSON.stringify(numbers);

  useEffect(() => {
    if (!complete) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      calculateProfit(numbers as ProfitInput)
        .then((r) => !cancelled && (setComputed(r), setError(null), setSaved(false)))
        .catch((e) => !cancelled && (setComputed(null), setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."))));
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // `key` stands for all the numbers; they are read from it, not listed one by one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, complete]);

  async function save() {
    try {
      await saveProfit(project.id, numbers as ProfitInput);
      setSaved(true);
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    }
  }

  const num = (label: string, value: string, set: (v: string) => void, hint?: string) => (
    <label className={field}>
      {t(label)}
      <Input inputMode="decimal" value={value} onChange={(e) => set(e.target.value)} />
      {hint ? <span className="block text-[11px] font-normal text-faint">{hint}</span> : null}
    </label>
  );

  const rateHint = !defaults
    ? undefined
    : defaults.returnRate !== null
      ? tf("Your shop's real return rate is {rate} ({orders} orders with a courier result).", { rate: formatPercent(defaults.returnRate * 100, 0), orders: defaults.returnRateOrders })
      : `${t("Not enough data yet")}: ${tf("{n} more orders with a courier result are needed to use your real return rate. Enter your own estimate.", { n: defaults.returnRateNeeded })}`;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{tf("Profit check for {product}", { product: project.productName })}</CardTitle>
          <CardDescription>{t("Fill in your numbers. Everything is worked out before you spend anything on ads.")}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {num("Product cost per piece (PKR)", cost, setCost, defaults?.costSource ? tf("From the quote of {vendor}.", { vendor: defaults.costSource }) : undefined)}
          {num("Selling price (PKR)", price, setPrice)}
          {num("Packing cost per order (PKR)", packing, setPacking)}
          {num("Courier fee per order (PKR)", courier, setCourier)}
          {num("Extra cost when a parcel comes back (PKR)", returnShipping, setReturnShipping, t("What the courier charges for the return trip."))}
          {num("Expected return rate (%)", rate, setRate, rateHint)}
          {num("Planned ad budget (PKR)", budget, setBudget)}
        </CardContent>
      </Card>

      <div aria-live="polite">{error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}</div>

      {result ? (
        <>
          <p className="text-xs font-medium text-muted">{t("Estimate from your numbers")}: {t("it is only as good as the numbers you typed.")}</p>
          {result.warnings.filter((w) => w !== "no_budget").map((w) => <Warning key={w} code={w} />)}
          <section aria-label={t("Profit results")} className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard label="Profit per delivered order" value={<Money value={result.profitDelivered} />} delta={null} icon={Wallet} />
            <KpiCard label="Profit per order placed, after returns" value={<Money value={result.profitPerOrderPlaced} />} delta={null}
              note={result.margin === null ? undefined : tf("{margin} of the price", { margin: formatPercent(result.margin * 100, 1) })} icon={Banknote} />
            <KpiCard label="Break-even ROAS" value={result.breakEvenRoas === null ? t("Not possible") : `${result.breakEvenRoas}x`} delta={null}
              note={t("Sales per rupee of ads needed to break even")} icon={Target} />
            <KpiCard label="Break-even cost per purchase" value={result.breakEvenCostPerPurchase === null ? t("Not possible") : <Money value={result.breakEvenCostPerPurchase} />} delta={null}
              note={t("The most one ad purchase may cost")} icon={Calculator} />
          </section>
          <Card>
            <CardContent className="space-y-1 pt-5 text-sm text-ink-2">
              <p>{tf("A returned order costs you {amount}.", { amount: formatNumber(Math.round(result.lossReturned)) + " PKR" })}</p>
              {result.ordersToRecoverBudget !== null
                ? <p>{tf("You need {count} orders to earn back your ad budget.", { count: formatNumber(result.ordersToRecoverBudget) })}</p>
                : result.warnings.includes("no_budget") ? <Warning code="no_budget" /> : <p>{t("The ad budget cannot be earned back at this profit.")}</p>}
              <div className="pt-2">
                <Button onClick={save}><Save className="h-4 w-4" aria-hidden="true" />{t("Save these numbers to the project")}</Button>
                {saved ? <span className="ml-3 text-xs text-success">{t("Saved. After launch they are compared with your real orders.")}</span> : null}
              </div>
            </CardContent>
          </Card>
        </>
      ) : !error ? <p className="text-sm text-muted">{t("Fill in every number above to see the result.")}</p> : null}

      <details className="rounded-2xl border border-line bg-surface p-4 text-sm text-ink-2">
        <summary className="cursor-pointer rounded font-medium text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40">{t("How these numbers are worked out")}</summary>
        <ul className="mt-3 list-disc space-y-1.5 pl-5">
          <li>{t("Delivered order: price minus product cost, packing and courier fee.")}</li>
          <li>{t("Returned order: you lose the packing, the courier fee and the return trip. The product goes back on the shelf, so its cost is not lost.")}</li>
          <li>{t("Profit per order placed = (share delivered x delivered profit) minus (share returned x loss on a return).")}</li>
          <li>{t("Break-even cost per purchase = that profit. Break-even ROAS = price divided by it.")}</li>
        </ul>
      </details>
    </div>
  );
}

function Warning({ code }: { code: string }) {
  const { t } = useLanguage();
  const w = WARNINGS[code];
  if (!w) return null;
  const Icon = w.icon;
  return (
    <div role="note" className={`flex items-start gap-3 rounded-xl border px-4 py-3 text-sm text-ink ${w.className}`}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <p>{t(w.text)}</p>
    </div>
  );
}

