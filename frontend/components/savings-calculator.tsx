"use client";

import { useEffect, useState } from "react";
import { Money } from "@/components/money";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input } from "@/components/ui/input";
import { useCurrency } from "@/lib/currency";
import { useLanguage } from "@/lib/i18n";
import type { SavingsCounts } from "@/lib/types";
import { formatDate, formatNumber, formatPercent } from "@/lib/utils";

type Flag = "high" | "mediumHigh";
const STORAGE_KEY = "ciq_shipping_cost";

/**
 * "How much could this have saved?" The numbers are counts from the TEST period (orders the model
 * had not seen); the only thing typed here is the shipping cost, so the money is simply
 *   flagged orders that really came back x shipping cost.
 * It is an estimate on past data and says so on screen.
 */
export function SavingsCalculator({
  high,
  mediumHigh,
}: {
  high: SavingsCounts | null;
  mediumHigh: SavingsCounts | null;
}) {
  const { t, tf } = useLanguage();
  const { state } = useCurrency();
  const [cost, setCost] = useState("");
  const [flag, setFlag] = useState<Flag>("high");

  // Remember the typed cost on this device only (never sent anywhere).
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (saved) setCost(saved);
    } catch {
      // Storage blocked: the field simply starts empty.
    }
  }, []);
  function changeCost(value: string) {
    setCost(value);
    try {
      window.localStorage.setItem(STORAGE_KEY, value);
    } catch {
      // The value just won't be remembered.
    }
  }

  const counts = flag === "high" ? high : mediumHigh;
  if (!counts) return null;
  const typed = cost.trim() === "" ? null : Number(cost);
  const valid = typed !== null && Number.isFinite(typed) && typed >= 0 && typed <= 1_000_000;
  const share = counts.flaggedOrders > 0 ? counts.flaggedReturned / counts.flaggedOrders : null;
  const caught = counts.totalReturned > 0 ? counts.flaggedReturned / counts.totalReturned : null;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm font-medium text-ink-2">
          {tf("Shipping cost per parcel, both ways ({currency})", { currency: state.source })}
          <Input
            type="number"
            inputMode="decimal"
            min={0}
            step="any"
            value={cost}
            onChange={(event) => changeCost(event.target.value)}
            placeholder="400"
            className="mt-1"
            aria-describedby="savings-note"
          />
        </label>
        <div>
          <p className="text-sm font-medium text-ink-2">{t("Which orders to flag")}</p>
          <div className="mt-1">
            <FilterPills
              label={t("Which orders to flag")}
              options={[
                { value: "high" as const, label: t("High risk only") },
                { value: "mediumHigh" as const, label: t("High and Medium risk") },
              ]}
              value={flag}
              onChange={setFlag}
            />
          </div>
        </div>
      </div>

      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-line bg-surface-2/60 p-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-muted">{t("Orders flagged")}</dt>
          <dd className="mt-1 text-2xl font-semibold tabular-nums">{formatNumber(counts.flaggedOrders)}</dd>
          <dd className="text-xs text-muted">
            {tf("{returned} really came back ({share})", {
              returned: formatNumber(counts.flaggedReturned),
              share: share === null ? "-" : formatPercent(share * 100),
            })}
          </dd>
        </div>
        <div className="rounded-xl border border-line bg-surface-2/60 p-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-muted">{t("False alarms")}</dt>
          <dd className="mt-1 text-2xl font-semibold tabular-nums">{formatNumber(counts.falseAlarms)}</dd>
          <dd className="text-xs text-muted">{t("Flagged, but delivered fine")}</dd>
        </div>
        <div className="rounded-xl border border-accent/40 bg-accent/10 p-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-muted">{t("Estimated cost avoided")}</dt>
          <dd className="mt-1 text-2xl font-semibold tabular-nums">
            {valid ? <Money value={counts.flaggedReturned * typed} /> : <span className="text-faint">—</span>}
          </dd>
          <dd className="text-xs text-muted">
            {valid ? (
              <>
                {t("All returns in this period cost")} <Money value={counts.totalReturned * typed} />
              </>
            ) : (
              t("Enter the shipping cost to see it")
            )}
          </dd>
        </div>
      </dl>

      <p className="text-xs text-muted">
        {caught === null
          ? null
          : tf("The flagged orders include {share} of all returned orders in this period.", {
              share: formatPercent(caught * 100),
            })}
      </p>
      <p id="savings-note" className="rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
        <strong>{t("This is an estimate on past orders, not a promise.")}</strong>{" "}
        {tf(
          "It uses {orders} orders from {start} to {end} that the model had not seen, and assumes every flagged order that came back would have been stopped.",
          {
            orders: formatNumber(counts.testOrders),
            start: formatDate(counts.testStart),
            end: formatDate(counts.testEnd),
          },
        )}
      </p>
    </div>
  );
}
