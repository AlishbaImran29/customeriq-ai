import Link from "next/link";
import { ArrowRight, PackageX } from "lucide-react";
import { load } from "@/components/data-state";
import { T } from "@/components/t";
import { Card } from "@/components/ui/card";
import { getOrderRisk } from "@/lib/api/customer-intelligence";
import { formatNumber } from "@/lib/utils";

/**
 * Small card for the main dashboard: how many recent orders need checking. It sits beside the
 * other figures but never breaks them: if Order Risk cannot be loaded, nothing is shown here.
 */
export async function OrderRiskCard() {
  const result = await load(() => getOrderRisk(1));
  if (!result.ok || result.data.meta.source === "demo" || !result.data.meta.asOf) return null;
  const { model, levelCounts, windowDays } = result.data;
  const available = model.status === "available";
  const risky = levelCounts.High + levelCounts.Medium;

  return (
    <Card className="p-4">
      <Link
        href="/order-risk"
        className="flex items-center justify-between gap-4 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
      >
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-accent/10 p-2 text-accent">
            <PackageX className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted">
              <T>Order Risk</T>
            </p>
            {available ? (
              <p className="text-sm text-ink-2">
                <strong className="text-2xl font-semibold tabular-nums text-ink">{formatNumber(risky)}</strong>{" "}
                <T>risky orders need checking</T> · <T>High</T> {formatNumber(levelCounts.High)}, <T>Medium</T>{" "}
                {formatNumber(levelCounts.Medium)} ({windowDays} <T>days</T>)
              </p>
            ) : (
              <p className="text-sm text-ink-2">
                <T>Not available yet</T> · <span className="text-muted"><T>See why</T></span>
              </p>
            )}
          </div>
        </div>
        <ArrowRight className="h-5 w-5 shrink-0 text-muted" aria-hidden="true" />
      </Link>
    </Card>
  );
}
