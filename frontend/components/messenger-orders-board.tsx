"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Loader2, Search, Truck } from "lucide-react";
import { MessageStatusBadge, MessengerGate, Reason, fieldClass, formatWhen } from "@/components/messenger-bits";
import { Money } from "@/components/money";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import { ORDER_STATUSES, changeOrderStatus, listOrders, orderTimeline, type OrderRow, type OrderStatus, type StatusResult, type Timeline } from "@/lib/api/messaging";
import { reasonPhrase } from "@/lib/messenger-text";
import { fmt } from "@/lib/format";

const STATUS_LABEL: Record<OrderStatus, string> = {
  confirmed: "Confirmed", dispatched: "Dispatched", in_transit: "In transit", out_for_delivery: "Out for delivery", delivered: "Delivered", returned: "Returned",
};

/**
 * The order status board. Change an order's status by hand (a courier file or Shopify can do it too) and the customer is told on the
 * channels they agreed to, in their language. Going back a step, or setting the same status again, never sends anything.
 */
export function MessengerOrdersBoard() {
  return (
    <MessengerGate>
      <OrdersContent />
    </MessengerGate>
  );
}

function OrdersContent() {
  const [rows, setRows] = useState<OrderRow[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listOrders(search || undefined)
      .then((r) => !cancelled && (setRows(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [search, version]);

  if (failed) return <ErrorState title="Could not load the orders" description="Please check your connection and reload the page." />;
  return (
    <div className="space-y-5">
      <Card>
        <CardContent className="pt-5">
          <form onSubmit={(e) => { e.preventDefault(); setSearch(typed.trim()); }} className="flex flex-col gap-3 sm:flex-row sm:items-end" noValidate>
            <label className={`${fieldClass} flex-1`}>Search by order number, product, customer or phone<Input value={typed} onChange={(e) => setTyped(e.target.value)} maxLength={80} /></label>
            <Button type="submit" variant="secondary"><Search className="h-4 w-4" aria-hidden="true" />Search</Button>
          </form>
        </CardContent>
      </Card>
      {!rows ? <Skeleton className="h-48 w-full" /> : rows.length === 0 ? <p className="text-sm text-muted">No orders found.</p> : (
        <ul className="space-y-3">
          {rows.map((o) => <OrderCard key={o.id} order={o} onChanged={() => setVersion((v) => v + 1)} />)}
        </ul>
      )}
    </div>
  );
}

function OrderCard({ order, onChanged }: { order: OrderRow; onChanged: () => void }) {
  const [status, setStatus] = useState<OrderStatus>(order.status ?? "confirmed");
  const [courier, setCourier] = useState("");
  const [tracking, setTracking] = useState("");
  const [notify, setNotify] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<StatusResult | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);

  async function apply() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await changeOrderStatus(order.id, { status, courier: courier.trim() || undefined, trackingNumber: tracking.trim() || undefined, notify }));
      setTimeline(null);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleTimeline() {
    setTimeline(timeline ? null : await orderTimeline(order.id).catch(() => null));
  }

  return (
    <li>
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">
            {order.orderNumber}
            <span className="inline-flex items-center gap-1 rounded-full bg-surface-3 px-2 py-0.5 text-[11px] font-medium text-ink-2">
              <Truck className="h-3 w-3" aria-hidden="true" />
              {order.status ? STATUS_LABEL[order.status] : "No status yet"}
            </span>
          </CardTitle>
          <CardDescription>
            {order.customerName}{order.phone ? ` · ${order.phone}` : ""} · <Money value={order.amount} />{order.paymentType === "cod" ? ` · ${"Cash on delivery"}` : ""}
            {order.products ? ` · ${order.products}` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className={fieldClass}>New status
              <Select value={status} onChange={(e) => setStatus(e.target.value as OrderStatus)} className="w-full">
                {ORDER_STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
              </Select>
            </label>
            <label className={fieldClass}>Courier (optional)<Input value={courier} onChange={(e) => setCourier(e.target.value)} maxLength={60} /></label>
            <label className={fieldClass}>Tracking number (optional)<Input value={tracking} onChange={(e) => setTracking(e.target.value)} maxLength={80} /></label>
            <label className="flex items-end gap-2 pb-2 text-sm text-ink-2">
              <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} className="h-4 w-4 accent-[var(--color-accent)]" />
              Tell the customer
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-3" aria-live="polite">
            <Button onClick={apply} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}Change status</Button>
            <button type="button" onClick={toggleTimeline} className="inline-flex items-center gap-1 rounded text-xs font-medium text-accent underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40">
              {timeline ? <ChevronUp className="h-3 w-3" aria-hidden="true" /> : <ChevronDown className="h-3 w-3" aria-hidden="true" />}{timeline ? "Hide history" : fmt("History and messages ({n})", { n: order.messages })}
            </button>
            {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
          </div>
          {result ? <ResultNote result={result} /> : null}
          {timeline ? (
            <div className="space-y-2 rounded-xl border border-line bg-surface-2 p-3 text-sm">
              {timeline.events.length === 0 ? <p className="text-muted">No status recorded yet.</p> : (
                <ul className="space-y-1 text-ink-2">
                  {timeline.events.map((e, i) => <li key={i}>{formatWhen(e.at)} · {STATUS_LABEL[e.status]} · {e.source}{e.courier ? ` · ${e.courier}` : ""}{e.trackingNumber ? ` · ${e.trackingNumber}` : ""}</li>)}
                </ul>
              )}
              {timeline.messages.map((m) => (
                <p key={m.id} className="border-t border-line pt-2 text-xs text-ink-2">
                  <MessageStatusBadge status={m.status} /> {m.channel === "whatsapp" ? "WhatsApp" : "Email"}: {m.error ? <Reason code={m.error} /> : <span dir="auto">{m.text.slice(0, 120)}</span>}
                </p>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </li>
  );
}

function ResultNote({ result }: { result: StatusResult }) {
  if (!result.recorded) return <p className="text-sm text-muted">{result.reason ? (reasonPhrase(result.reason)?.text ? reasonPhrase(result.reason)!.text : "") : ""}</p>;
  if (!result.announced) return <p className="text-sm text-ink-2">Status saved. {result.reason ? (reasonPhrase(result.reason)?.text ?? "") : ""}</p>;
  if (result.messages.length === 0) return <p className="text-sm text-warning">Status saved. There is no template for this status yet, so nobody was messaged.</p>;
  return (
    <ul className="space-y-1 text-sm">
      <li className="text-success">Status saved.</li>
      {result.messages.map((m) => (
        <li key={m.id} className="flex flex-wrap items-center gap-2 text-ink-2">
          <MessageStatusBadge status={m.status} />
          {m.channel === "whatsapp" ? "WhatsApp" : "Email"}
          {m.error ? <span className="text-warning"><Reason code={m.error} /></span> : m.status === "queued" ? <span>{fmt("Held until {time} (quiet hours).", { time: formatWhen(m.nextAttemptAt) })}</span> : null}
        </li>
      ))}
    </ul>
  );
}
