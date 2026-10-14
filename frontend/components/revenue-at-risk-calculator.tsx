"use client";

import { useMemo, useState } from "react";
import { formatCurrency } from "@/lib/utils";

export function RevenueAtRiskCalculator() {
  const [customers, setCustomers] = useState(3680);
  const [avgOrder, setAvgOrder] = useState(67);
  const [churnRate, setChurnRate] = useState(14.2);

  const atRisk = useMemo(
    () => customers * avgOrder * (churnRate / 100),
    [avgOrder, churnRate, customers],
  );

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-4">
        <label className="block text-sm">
          <span className="text-slate-600">At-risk customers</span>
          <input
            type="range"
            min={500}
            max={8000}
            value={customers}
            onChange={(event) => setCustomers(Number(event.target.value))}
            className="mt-2 w-full accent-teal-600"
          />
          <span className="text-xs text-slate-500">{customers.toLocaleString()}</span>
        </label>
        <label className="block text-sm">
          <span className="text-slate-600">Average order value</span>
          <input
            type="range"
            min={20}
            max={200}
            value={avgOrder}
            onChange={(event) => setAvgOrder(Number(event.target.value))}
            className="mt-2 w-full accent-teal-600"
          />
          <span className="text-xs text-slate-500">{formatCurrency(avgOrder)}</span>
        </label>
        <label className="block text-sm">
          <span className="text-slate-600">Expected churn rate</span>
          <input
            type="range"
            min={1}
            max={40}
            step={0.1}
            value={churnRate}
            onChange={(event) => setChurnRate(Number(event.target.value))}
            className="mt-2 w-full accent-teal-600"
          />
          <span className="text-xs text-slate-500">{churnRate.toFixed(1)}%</span>
        </label>
      </div>
      <div className="rounded-2xl bg-slate-950 p-5 text-white">
        <p className="text-xs uppercase tracking-wide text-slate-400">
          Estimated revenue at risk
        </p>
        <p className="mt-2 text-3xl font-semibold">{formatCurrency(atRisk)}</p>
        <p className="mt-3 text-sm text-slate-300">
          Sample calculator using documentation inputs. This is not a live
          forecast from the ML layer.
        </p>
      </div>
    </div>
  );
}
