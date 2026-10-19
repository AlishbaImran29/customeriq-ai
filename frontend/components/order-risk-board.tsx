"use client";

import { useState } from "react";
import { Money } from "@/components/money";
import { MessageLanguagePicker, WhatsAppButton } from "@/components/whatsapp-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FilterPills } from "@/components/ui/filter-pills";
import { useLanguage } from "@/lib/i18n";
import type { MessageLanguage } from "@/lib/whatsapp";
import type { OrderRiskLevel, OrderRiskOverview, OrderRiskReason, OrderRiskRow } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const PAGE = 50;
const LEVEL_LABEL: Record<OrderRiskLevel, string> = { Low: "Low risk", Medium: "Medium risk", High: "High risk" };
// Each level has its own icon (from Badge) AND a word, so the level never depends on colour alone.
const LEVEL_VARIANT = { Low: "success", Medium: "warning", High: "danger" } as const;

type Filter = OrderRiskLevel | "all";

/** The "Why?" of one order: the strongest reason, and the others on request (or all of them on a phone). */
function Reasons({ reasons, all = false }: { reasons: OrderRiskReason[]; all?: boolean }) {
  const { t, tf } = useLanguage();
  if (reasons.length === 0) {
    return <p className="text-xs text-muted">{t("No single factor stands out.")}</p>;
  }
  const show = (r: OrderRiskReason) => tf(r.template, r.params);
  if (all || reasons.length === 1) {
    return (
      <ul className="space-y-1 text-sm text-ink-2">
        {reasons.map((r) => (
          <li key={r.template}>{show(r)}</li>
        ))}
      </ul>
    );
  }
  return (
    <div className="text-sm text-ink-2">
      <p>{show(reasons[0])}</p>
      <details className="mt-1">
        <summary className="cursor-pointer text-xs text-accent hover:underline">
          {t("More reasons")} ({reasons.length - 1})
        </summary>
        <ul className="mt-1 space-y-1">
          {reasons.slice(1).map((r) => (
            <li key={r.template}>{show(r)}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function RiskBadge({ row }: { row: OrderRiskRow }) {
  const { t } = useLanguage();
  return (
    <div className="flex items-center gap-2">
      <Badge variant={LEVEL_VARIANT[row.level]}>{t(LEVEL_LABEL[row.level])}</Badge>
      <span className="text-sm tabular-nums text-ink-2" title={t("The model's estimate, not a fact")}>
        {Math.round(row.probability * 100)}%
      </span>
    </div>
  );
}

function Action({ row, language }: { row: OrderRiskRow; language: MessageLanguage }) {
  const { t } = useLanguage();
  return (
    <div className="flex flex-col items-start gap-2">
      <p className="text-sm text-ink">{t(row.action)}</p>
      <WhatsAppButton
        level={row.level}
        orderId={row.orderId}
        amount={row.amount}
        phone={row.whatsappPhone}
        messageLanguage={language}
        showReason={false}
      />
    </div>
  );
}

/** Recent orders with risk level, reasons and the action. A table on wide screens, cards on a phone (no sideways scrolling). */
export function OrderRiskBoard({ data }: { data: OrderRiskOverview }) {
  const { t, tf } = useLanguage();
  const [filter, setFilter] = useState<Filter>("all");
  const [language, setLanguage] = useState<MessageLanguage>("en");
  const [shown, setShown] = useState(PAGE);

  const rows = data.orders.filter((o) => filter === "all" || o.level === filter);
  const visible = rows.slice(0, shown);
  const counts = data.levelCounts;
  const options = [
    { value: "all" as const, label: t("All"), count: data.windowOrders },
    { value: "High" as const, label: t("High risk"), count: counts.High },
    { value: "Medium" as const, label: t("Medium risk"), count: counts.Medium },
    { value: "Low" as const, label: t("Low risk"), count: counts.Low },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <FilterPills
          label={t("Filter by risk level")}
          options={options}
          value={filter}
          onChange={(value) => {
            setFilter(value);
            setShown(PAGE);
          }}
        />
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted">{t("Message language")}</span>
          <MessageLanguagePicker value={language} onChange={setLanguage} />
        </div>
      </div>

      {visible.some((row) => row.level !== "Low" && !row.whatsappPhone) ? (
        <p className="text-xs text-muted">
          {t("Some orders have no usable phone number in your data, so their WhatsApp button is disabled.")}
        </p>
      ) : null}

      {data.truncated ? (
        <p className="text-xs text-muted">
          {tf("Showing the first {count} orders. The riskiest come first.", { count: data.orders.length })}
        </p>
      ) : null}

      {visible.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface-2/60 px-4 py-6 text-center text-sm text-muted">
          {t("No orders at this risk level in this period.")}
        </p>
      ) : (
        <>
          {/* Wide screens: a table. */}
          <div className="hidden md:block">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">{t("Recent orders with their risk of being returned")}</caption>
              <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th scope="col" className="px-3 py-3 font-medium">{t("Order")}</th>
                  <th scope="col" className="px-3 py-3 font-medium">{t("Amount")}</th>
                  <th scope="col" className="px-3 py-3 font-medium">{t("Risk")}</th>
                  <th scope="col" className="px-3 py-3 font-medium">{t("Why?")}</th>
                  <th scope="col" className="px-3 py-3 font-medium">{t("What to do")}</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr key={row.orderId} className="border-b border-line/60 align-top last:border-0 hover:bg-surface-2/60">
                    <td className="px-3 py-3">
                      <p className="font-medium text-ink">{row.orderId}</p>
                      <p className="text-xs text-muted">
                        {row.customerName} · {formatDate(row.orderDate)}
                      </p>
                    </td>
                    <td className="px-3 py-3 tabular-nums"><Money value={row.amount} /></td>
                    <td className="px-3 py-3"><RiskBadge row={row} /></td>
                    <td className="max-w-xs px-3 py-3"><Reasons reasons={row.reasons} /></td>
                    <td className="px-3 py-3"><Action row={row} language={language} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Phones: one card per order. */}
          <ul className="space-y-3 md:hidden">
            {visible.map((row) => (
              <li key={row.orderId} className="space-y-3 rounded-xl border border-line bg-surface-2/40 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-medium text-ink">{row.orderId}</p>
                    <p className="text-xs text-muted">
                      {row.customerName} · {formatDate(row.orderDate)}
                    </p>
                  </div>
                  <p className="shrink-0 text-sm font-medium tabular-nums"><Money value={row.amount} /></p>
                </div>
                <RiskBadge row={row} />
                <div>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">{t("Why?")}</p>
                  <Reasons reasons={row.reasons} all />
                </div>
                <Action row={row} language={language} />
              </li>
            ))}
          </ul>

          {rows.length > shown ? (
            <div className="flex justify-center">
              <Button variant="secondary" onClick={() => setShown((n) => n + PAGE)}>
                {tf("Show {count} more", { count: Math.min(PAGE, rows.length - shown) })}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
