"use client";

import { FlaskConical, ShieldOff } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import type { OrderRiskModel } from "@/lib/types";
import { formatDate, formatNumber, formatPercent } from "@/lib/utils";

const pct = (value: number | null) => (value === null ? "-" : formatPercent(value * 100));
const score = (value: number | null) => (value === null ? "-" : value.toFixed(3));

/** Where the labels came from. Shown on the page because it decides what the model really learned. */
export function LabelSourceNote({ source }: { source: string | null }) {
  const { t } = useLanguage();
  const proxy = source === "proxy: cancellations";
  const courier = source === "courier data";
  return (
    <p className="text-xs text-muted">
      <strong className="text-ink-2">{t("Labels")}: {source ?? "-"}.</strong>{" "}
      {courier
        ? t("The model learned from real courier results (delivered or returned).")
        : proxy
          ? t(
              "The model learned from orders that were later cancelled in your files, used as a stand-in for refused or returned parcels. Add courier results below to learn from real delivery outcomes.",
            )
          : t("The model learned from a mix of courier results and cancelled orders.")}
    </p>
  );
}

/** The evidence behind a model that passed the trust rule. */
export function OrderRiskModelNote({ model }: { model: OrderRiskModel }) {
  const { t, tf } = useLanguage();
  return (
    <details className="rounded-xl border border-info/30 bg-info/10 px-3 py-2 text-sm text-info">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-medium">
        <FlaskConical className="h-4 w-4 shrink-0" aria-hidden="true" />
        {t("Order risk model: estimates, not facts. Tested on unseen orders.")}{" "}
        <span className="font-normal underline">{t("Details")}</span>
      </summary>
      <div className="mt-2 space-y-1 text-ink-2">
        <p>
          {model.metric}: {t("model")} <strong>{score(model.modelScore)}</strong>, {t("baseline")}{" "}
          <strong>{score(model.baselineScore)}</strong> ({t("baseline = the customer's own past return rate")}).
        </p>
        <p>
          {tf("Among the riskiest {share} of orders, {model} really came back (baseline: {baseline}).", {
            share: pct(model.topFraction),
            model: pct(model.modelPrecisionTop),
            baseline: pct(model.baselinePrecisionTop),
          })}
        </p>
        <p>
          {tf("Trained on {train} orders up to {end}, tested on {test} newer orders from {start}.", {
            train: formatNumber(model.trainRows),
            end: model.trainEnd ? formatDate(model.trainEnd) : "-",
            test: formatNumber(model.testRows),
            start: model.splitDate ? formatDate(model.splitDate) : "-",
          })}{" "}
          {tf("Orders newer than {days} days are not used, because they may still be cancelled.", {
            days: model.maturityDays,
          })}
        </p>
        <p>
          {tf("Levels: Low under {low}, High over {high}, Medium in between.", {
            low: pct(model.lowBelow),
            high: pct(model.highAbove),
          })}
        </p>
        <LabelSourceNote source={model.labelSource} />
      </div>
    </details>
  );
}

/** The rule says no: nothing is predicted, and the page says why and shows the evidence. */
export function OrderRiskUnavailable({ model }: { model: OrderRiskModel }) {
  const { t, tf } = useLanguage();
  const compared = model.modelScore !== null && model.baselineScore !== null;
  return (
    <div className="rounded-2xl border border-warning/30 bg-warning/10 p-5 text-sm text-ink-2">
      <div className="flex items-start gap-3">
        <ShieldOff className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden="true" />
        <div className="space-y-2">
          <h2 className="text-base font-semibold text-ink">{t("Not available yet")}</h2>
          <p>{model.reason}</p>
          {compared ? (
            <p>
              {tf("Scores on orders it had not seen: model {model}, baseline {baseline} ({metric}).", {
                model: score(model.modelScore),
                baseline: score(model.baselineScore),
                metric: model.metric,
              })}
            </p>
          ) : null}
          <p className="text-muted">
            {t(
              "CustomerIQ AI shows an order's risk only when the model beats a simple baseline on orders it has not seen. Otherwise it shows nothing rather than an invented number.",
            )}
          </p>
          {model.labelSource ? <LabelSourceNote source={model.labelSource} /> : null}
        </div>
      </div>
    </div>
  );
}
