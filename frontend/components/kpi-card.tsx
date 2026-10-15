import { Card } from "@/components/ui/card";
import { cn, formatPercent } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

export function KpiCard({
  label,
  value,
  delta,
  deltaUnit = "%",
  invertDelta,
  unavailableReason,
  note,
  icon: Icon,
}: {
  label: string;
  /** Formatted value, or null when the metric is not available. */
  value: string | null;
  /** Change vs the previous period; null when there is not enough history. */
  delta: number | null;
  /** "%" for relative change, "pts" for change in a rate or score. */
  deltaUnit?: "%" | "pts";
  invertDelta?: boolean;
  /** Shown instead of the value when `value` is null. */
  unavailableReason?: string;
  /** Shown under the value when there is no change to show (e.g. a model estimate). */
  note?: string;
  icon: LucideIcon;
}) {
  const positive = delta !== null && (invertDelta ? delta < 0 : delta >= 0);
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {label}
          </p>
          {value === null ? (
            <>
              <p className="mt-2 text-lg font-semibold tracking-tight text-slate-400">
                Not available yet
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {unavailableReason ?? "Not available yet."}
              </p>
            </>
          ) : (
            <>
              <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
                {value}
              </p>
              {delta === null ? (
                <p className="mt-1 text-xs text-slate-500">{note ?? "Not enough history to compare"}</p>
              ) : (
                <p
                  className={cn(
                    "mt-1 text-xs font-medium",
                    positive ? "text-emerald-600" : "text-rose-600",
                  )}
                >
                  {delta > 0 ? "+" : ""}
                  {deltaUnit === "%" ? formatPercent(delta) : `${delta.toFixed(1)} pts`} vs last period
                </p>
              )}
            </>
          )}
        </div>
        <div className="rounded-xl bg-teal-50 p-2 text-teal-700">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
      </div>
    </Card>
  );
}
