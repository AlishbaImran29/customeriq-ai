"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Paperclip, Plus } from "lucide-react";
import { formatWhen } from "@/components/messenger-bits";
import { Money } from "@/components/money";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { API_MODE, ApiError } from "@/lib/api/config";
import { listOrders, type OrderRow } from "@/lib/api/messaging";
import { addEvidence, approveReturn, closeReturn, createReturn, getReturn, listReturns, receiveReturn, recordRefund, rejectReturn, type ReturnRow, type ReturnStatus } from "@/lib/api/returns";

const field = "flex flex-col gap-1 text-sm font-medium text-ink-2";
const LABEL: Record<ReturnStatus, string> = { requested: "New request", approved: "Approved", rejected: "Rejected", received: "Goods received", closed: "Closed" };

/** Return requests: approve or reject, choose refund / replacement, mark the goods received, and record refunds you paid. The app never sends money. */
export function ReturnsBoard() {
  if (API_MODE !== "live") return <p className="text-sm text-muted">Returns are saved in your database. Connect the backend to use them.</p>;
  return <ReturnsContent />;
}

function ReturnsContent() {
  const [show, setShow] = useState<"all" | ReturnStatus>("all");
  const [rows, setRows] = useState<ReturnRow[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listReturns(show === "all" ? undefined : show)
      .then((r) => !cancelled && (setRows(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [show, version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (failed) return <ErrorState title="Could not load the returns" description="Please check your connection and reload the page." />;
  return (
    <div className="space-y-5">
      <NewReturn onAdded={reload} />
      <FilterPills label="Filter by status" value={show} onChange={setShow}
        options={[{ value: "all" as const, label: "All" }, ...(Object.keys(LABEL) as ReturnStatus[]).map((s) => ({ value: s, label: LABEL[s] }))]} />
      {!rows ? <Skeleton className="h-40 w-full" /> : rows.length === 0 ? <p className="text-sm text-muted">No returns here.</p> : (
        <ul className="space-y-3">{rows.map((r) => <ReturnCard key={r.id} row={r} onChanged={reload} />)}</ul>
      )}
    </div>
  );
}

function NewReturn({ onAdded }: { onAdded: () => void }) {
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [orderId, setOrderId] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    listOrders().then((r) => setOrders(r.slice(0, 50))).catch(() => undefined);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createReturn(Number(orderId), reason.trim());
      setOrderId("");
      setReason("");
      onAdded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle>Record a return request</CardTitle><CardDescription>When a customer asks to send something back.</CardDescription></CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1.2fr_1.8fr_auto] sm:items-end" noValidate>
          <label className={field}>Order
            <Select value={orderId} onChange={(e) => setOrderId(e.target.value)} className="w-full"><option value="">Choose an order</option>{orders.map((o) => <option key={o.id} value={o.id}>{o.orderNumber} · {o.customerName}</option>)}</Select>
          </label>
          <label className={field}>Reason<Input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} /></label>
          <Button type="submit" disabled={busy || !orderId || reason.trim().length < 3}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}Add</Button>
          {error ? <p role="alert" className="text-sm text-danger sm:col-span-3">{error}</p> : null}
        </form>
      </CardContent>
    </Card>
  );
}

function ReturnCard({ row, onChanged }: { row: ReturnRow; onChanged: () => void }) {
  const [detail, setDetail] = useState<ReturnRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolution, setResolution] = useState<"refund" | "replacement" | "none">("refund");
  const [amount, setAmount] = useState(String(row.orderTotal));
  const [method, setMethod] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const shown = detail ?? row;

  async function run(work: () => Promise<unknown>, refresh = true) {
    setBusy(true);
    setError(null);
    try {
      await work();
      if (refresh) setDetail(await getReturn(row.id));
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li>
      <Card>
        <CardContent className="space-y-3 pt-5 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-ink">{row.orderNumber}</span> <span className="text-ink-2">{row.customerName}</span>
            <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[11px] font-medium text-ink-2">{LABEL[shown.status]}</span>
            <span className="ml-auto text-xs text-muted"><Money value={row.orderTotal} /> · {formatWhen(row.createdAt)}</span>
          </div>
          <p className="text-ink-2">{row.reason}</p>
          {shown.decisionNote ? <p className="text-xs text-muted">{shown.decisionNote}</p> : null}

          {shown.status === "requested" ? (
            <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto_auto] sm:items-end">
              <label className={field}>If approved
                <Select value={resolution} onChange={(e) => setResolution(e.target.value as typeof resolution)} className="w-full">
                  <option value="refund">Refund</option><option value="replacement">Send a replacement</option><option value="none">Nothing more</option>
                </Select>
              </label>
              {resolution === "refund" ? <label className={field}>Refund amount<Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" /></label> : <span />}
              <Button disabled={busy} onClick={() => run(() => approveReturn(row.id, resolution, resolution === "refund" ? Number(amount) : undefined))}>Approve</Button>
              <Button variant="ghost" disabled={busy} onClick={() => run(() => rejectReturn(row.id, window.prompt("Why? (optional)") ?? undefined))}>Reject</Button>
            </div>
          ) : null}
          {shown.status === "approved" ? (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" disabled={busy} onClick={() => run(() => receiveReturn(row.id, window.confirm("Are the goods fine to sell again? OK = put back on the shelf")))}>Goods received</Button>
            </div>
          ) : null}
          {shown.status === "received" ? <Button variant="secondary" disabled={busy} onClick={() => run(() => closeReturn(row.id))}>Close this return</Button> : null}

          {detail ? (
            <>
              {shown.refunds.map((f) => (
                <div key={f.id} className="rounded-xl border border-line bg-surface-2 p-3">
                  <p className="text-ink">Refund: <Money value={f.amount} /> · {f.status === "recorded" ? `${"paid back by you"}: ${f.method}${f.reference ? ` (${f.reference})` : ""}` : "waiting for you to pay it back"}</p>
                  {f.status === "requested" ? (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Input value={method} onChange={(e) => setMethod(e.target.value)} placeholder="How did you pay it? (JazzCash, bank...)" className="w-64" maxLength={60} />
                      <Button variant="secondary" disabled={busy || !method.trim()} onClick={() => run(() => recordRefund(f.id, method.trim()))}>I paid it: record</Button>
                    </div>
                  ) : null}
                  <p className="mt-1 text-[11px] text-muted">The app never sends money. Pay the customer yourself, then record it here.</p>
                </div>
              ))}
              <div className="flex flex-wrap items-center gap-2">
                <input ref={file} type="file" accept="image/png,image/jpeg,image/webp,video/mp4" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void run(() => addEvidence(row.id, f)); e.target.value = ""; }} />
                <Button variant="secondary" disabled={busy} onClick={() => file.current?.click()}><Paperclip className="h-4 w-4" aria-hidden="true" />Attach photo or video</Button>
                {shown.evidence.map((e) => e.url ? <a key={e.id} href={e.url} target="_blank" rel="noreferrer" className="text-xs font-medium text-accent underline underline-offset-2">{e.kind} #{e.id}</a> : <span key={e.id} className="text-xs text-muted">{e.kind} #{e.id}</span>)}
              </div>
              <ul className="space-y-1 text-xs text-ink-2">{shown.events.map((e, i) => <li key={i}>{formatWhen(e.at)} · {e.event.replace(/_/g, " ")}{e.by ? ` · ${e.by}` : ""}</li>)}</ul>
            </>
          ) : <button type="button" onClick={() => run(async () => undefined)} className="text-xs font-medium text-accent underline underline-offset-2">Show details</button>}
          <div aria-live="polite">{error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}</div>
        </CardContent>
      </Card>
    </li>
  );
}
