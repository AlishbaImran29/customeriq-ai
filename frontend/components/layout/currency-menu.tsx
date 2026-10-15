"use client";

import { Coins } from "lucide-react";
import { CURRENCIES, setCurrencies, useCurrency, type CurrencyCode } from "@/lib/currency";

const selectClass =
  "mt-1 w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40";

export function CurrencyMenu() {
  const { state } = useCurrency();

  const note =
    state.status === "loading"
      ? "Loading the exchange rate…"
      : state.status === "unavailable"
        ? `Could not load the ${state.source} → ${state.target} rate, so amounts are shown in ${state.source}.`
        : state.status === "ready" && state.rate
          ? `1 ${state.source} = ${state.rate.toLocaleString("en-US", { maximumFractionDigits: 4 })} ${state.target}${state.updated ? ` · rate from ${state.updated.replace(/ \+0000$/, " UTC")}` : ""}`
          : "No conversion: numbers are shown as imported.";

  return (
    <details className="group relative">
      <summary
        className="flex cursor-pointer list-none items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 [&::-webkit-details-marker]:hidden"
        aria-label="Currency settings"
      >
        <Coins className="h-3.5 w-3.5 text-teal-700" aria-hidden="true" />
        {state.status === "ready" ? state.target : state.source}
      </summary>
      <div className="absolute right-0 z-30 mt-2 w-72 rounded-xl border border-slate-200 bg-white p-3 text-left shadow-lg">
        <label className="block text-xs font-medium text-slate-600">
          My data is in
          <select
            className={selectClass}
            value={state.source}
            onChange={(event) => setCurrencies(event.target.value as CurrencyCode, state.target)}
          >
            {CURRENCIES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.code} · {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="mt-3 block text-xs font-medium text-slate-600">
          Show amounts in
          <select
            className={selectClass}
            value={state.target}
            onChange={(event) => setCurrencies(state.source, event.target.value as CurrencyCode)}
          >
            {CURRENCIES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.code} · {c.name}
              </option>
            ))}
          </select>
        </label>
        <p className="mt-3 text-xs text-slate-500">{note}</p>
        <p className="mt-1 text-[11px] text-slate-400">Rates are indicative, not for accounting.</p>
      </div>
    </details>
  );
}
