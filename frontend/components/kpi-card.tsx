import { Card } from "@/components/ui/card";
import { cn, formatPercent } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

export function KpiCard({
  label,
  value,
  delta,
  invertDelta,
  icon: Icon,
}: {
  label: string;
  value: string;
  delta: number;
  invertDelta?: boolean;
  icon: LucideIcon;
}) {
  const positive = invertDelta ? delta < 0 : delta >= 0;
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            {label}
          </p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
            {value}
          </p>
          <p
            className={cn(
              "mt-1 text-xs font-medium",
              positive ? "text-emerald-600" : "text-rose-600",
            )}
          >
            {delta > 0 ? "+" : ""}
            {formatPercent(delta)} vs last period
          </p>
        </div>
        <div className="rounded-xl bg-teal-50 p-2 text-teal-700">
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </Card>
  );
}
