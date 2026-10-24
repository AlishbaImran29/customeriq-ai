"use client";

import { useCallback, useEffect, useState } from "react";
import { Phone } from "lucide-react";
import { MessengerGate, formatWhen } from "@/components/messenger-bits";
import { Money } from "@/components/money";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import { listCod, resolveCod, type CodRow, type CodState } from "@/lib/api/messaging";
import { useLanguage } from "@/lib/i18n";

type Show = "all" | CodState;
const STATE_LABEL: Record<CodState, string> = { awaiting: "Waiting for an answer", confirmed: "Confirmed", cancelled: "Cancelled", needs_call: "Needs a phone call" };
const STATE_TONE: Record<CodState, string> = { awaiting: "bg-surface-3 text-ink-2", confirmed: "bg-success/15 text-success", cancelled: "bg-danger/15 text-danger", needs_call: "bg-warning/15 text-warning" };

/**
 * Cash-on-delivery orders the customer was asked to confirm on WhatsApp. YES confirms, NO cancels (and gives the reserved stock
 * back). No answer in time means "needs a phone call", and Order Risk then shows that order one level higher.
 */
export function MessengerCodBoard() {
  return (
    <MessengerGate>
      <CodContent />
    </MessengerGate>
  );
}

function CodContent() {
  const { t } = useLanguage();
  const [show, setShow] = useState<Show>("all");
  const [rows, setRows] = useState<CodRow[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listCod(show === "all" ? undefined : show)
      .then((r) => !cancelled && (setRows(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [show, version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (failed) return <ErrorState title={t("Could not load the COD confirmations")} description={t("Please check your connection and reload the page.")} />;
  return (
    <div className="space-y-5">
      <FilterPills
        label={t("Filter by state")} value={show} onChange={setShow}
        options={[
          { value: "all" as Show, label: t("All") }, { value: "needs_call" as Show, label: t("Needs a phone call") }, { value: "awaiting" as Show, label: t("Waiting for an answer") },
          { value: "confirmed" as Show, label: t("Confirmed") }, { value: "cancelled" as Show, label: t("Cancelled") },
        ]}
      />
      {!rows ? <Skeleton className="h-40 w-full" /> : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("No COD orders have been asked to confirm yet. Approve the cod_confirmation template in Templates, then add a COD order for a customer who agreed to WhatsApp.")}</p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">{rows.map((r) => <CodCard key={r.orderId} row={r} onChanged={reload} />)}</ul>
      )}
    </div>
  );
}

function CodCard({ row, onChanged }: { row: CodRow; onChanged: () => void }) {
  const { t, tf } = useLanguage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = row.state === "awaiting" || row.state === "needs_call";

  async function resolve(result: "confirmed" | "cancelled") {
    setBusy(true);
    setError(null);
    try {
      await resolveCod(row.orderId, result);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li>
      <Card className="h-full">
        <CardContent className="space-y-2 pt-5 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-ink">{row.orderNumber}</span>
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATE_TONE[row.state]}`}>{t(STATE_LABEL[row.state])}</span>
            <span className="ml-auto text-xs text-muted"><Money value={row.amount} /></span>
          </div>
          <p className="text-ink-2">{row.customerName}{row.phone ? ` · ${row.phone}` : ""}</p>
          <p className="text-xs text-muted">
            {tf("Asked {time}", { time: formatWhen(row.askedAt) })}
            {row.state === "awaiting" ? ` · ${tf("answer due by {time}", { time: formatWhen(row.deadlineAt) })}` : ""}
            {row.answeredAt ? ` · ${row.resolvedBy === "seller" ? t("recorded by you") : t("customer replied")}${row.replyText ? `: ${row.replyText}` : ""}` : ""}
          </p>
          {open ? (
            <div className="flex flex-wrap items-center gap-2">
              {row.state === "needs_call" ? <span className="inline-flex items-center gap-1 text-xs text-warning"><Phone className="h-3 w-3" aria-hidden="true" />{t("Phone the customer, then record the result:")}</span> : null}
              <Button variant="secondary" disabled={busy} onClick={() => resolve("confirmed")} className="!px-2.5 !py-1 text-xs">{t("Customer confirmed")}</Button>
              <Button variant="ghost" disabled={busy} onClick={() => resolve("cancelled")} className="!px-2.5 !py-1 text-xs">{t("Customer cancelled")}</Button>
            </div>
          ) : null}
          <div aria-live="polite">{error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}</div>
        </CardContent>
      </Card>
    </li>
  );
}
