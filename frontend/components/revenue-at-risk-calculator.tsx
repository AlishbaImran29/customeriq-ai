"use client";

import { useState } from "react";
import { formatCurrency, formatNumber } from "@/lib/utils";

export type CalculatorDefaults = {
  /** Customers considered at risk. */
  customers: number;
  /** Average spend per customer over a year. */
  yearlySpend: number;
  /** Share of them expected to leave, in percent. */
  share: number;
  /** Where the starting numbers come from (shown to the reader). */
  source: string;
};

/** Round up to a "nice" slider maximum, at least `floor`. */
function sliderMax(value: number, factor: number, floor: number) {
  const raw = Math.max(floor, value * factor);
  const magnitude = 10 ** Math.max(0, Math.floor(Math.log10(raw)) - 1);
  return Math.ceil(raw / magnitude) * magnitude;
}

/**
 * Scenario tool: revenue at risk = customers at risk x their average yearly spend x the
 * share expected to leave. Runs in the browser; it is a "what if", not a forecast.
 */
export function RevenueAtRiskCalculator({ defaults }: { defaults: CalculatorDefaults }) {
  const [customers, setCustomers] = useState(defaults.customers);
  const [yearlySpend, setYearlySpend] = useState(Math.round(defaults.yearlySpend));
  const [share, setShare] = useState(defaults.share);

  const atRisk = customers * yearlySpend * (share / 100);
  const maxCustomers = sliderMax(defaults.customers, 2, 100);
  const maxSpend = sliderMax(defaults.yearlySpend, 3, 100);

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-4">
        <label className="block text-sm">
          <span className="text-slate-600">Customers at risk</span>
          <input
            type="range"
            min={0}
            max={maxCustomers}
            step={Math.max(1, Math.round(maxCustomers / 200))}
            value={customers}
            onChange={(event) => setCustomers(Number(event.target.value))}
            className="mt-2 w-full accent-teal-600"
          />
          <span className="text-xs text-slate-500">{formatNumber(customers)}</span>
        </label>
        <label className="block text-sm">
          <span className="text-slate-600">Average spend per customer per year</span>
          <input
            type="range"
            min={0}
            max={maxSpend}
            step={Math.max(1, Math.round(maxSpend / 200))}
            value={yearlySpend}
            onChange={(event) => setYearlySpend(Number(event.target.value))}
            className="mt-2 w-full accent-teal-600"
          />
          <span className="text-xs text-slate-500">{formatCurrency(yearlySpend)}</span>
        </label>
        <label className="block text-sm">
          <span className="text-slate-600">Share of them expected to leave</span>
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={share}
            onChange={(event) => setShare(Number(event.target.value))}
            className="mt-2 w-full accent-teal-600"
          />
          <span className="text-xs text-slate-500">{share}%</span>
        </label>
        <p className="text-xs text-slate-500">Starting values: {defaults.source}. Move the sliders to try other scenarios.</p>
      </div>
      <div className="rounded-2xl bg-slate-950 p-5 text-white" aria-live="polite">
        <p className="text-xs uppercase tracking-wide text-slate-400">Yearly revenue at risk in this scenario</p>
        <p className="mt-2 text-3xl font-semibold">{formatCurrency(atRisk)}</p>
        <p className="mt-3 text-sm text-slate-300">
          = {formatNumber(customers)} customers × {formatCurrency(yearlySpend)} a year × {share}% leaving. A
          &ldquo;what if&rdquo; tool, not a forecast.
        </p>
      </div>
    </div>
  );
}
