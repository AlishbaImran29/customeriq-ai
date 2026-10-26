"use client";

import { useId, useState } from "react";
import { CheckCircle2, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { addPayment } from "@/lib/api/cash";
import { ApiError } from "@/lib/api/config";
import { fmt } from "@/lib/format";

const today = () => new Date().toISOString().slice(0, 10);

/** Add one courier payment by hand: courier, date, amount (PKR), and optionally a reference and the orders it paid for. */
export function PaymentForm({ couriers, onSaved }: { couriers: string[]; onSaved: () => void }) {
  const uid = useId();
  const [courier, setCourier] = useState("");
  const [date, setDate] = useState(today());
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [orders, setOrders] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(null);
    const number = Number(amount.replace(/,/g, ""));
    if (!courier.trim()) return setError("Enter the courier name.");
    if (!Number.isFinite(number) || number <= 0) return setError("Enter an amount of more than 0.");
    setBusy(true);
    try {
      const result = await addPayment({
        courierName: courier.trim(), paymentDate: date, amount: number,
        reference: reference.trim() || undefined, orderIds: orders.trim() || undefined,
      });
      setSaved(fmt("Saved a payment from {courier}.", { courier: result.courier }));
      setAmount("");
      setReference("");
      setOrders("");
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const field = "space-y-1 text-xs font-medium text-muted";
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2" noValidate>
      <label className={field}>
        Courier name
        <Input list={`${uid}-couriers`} value={courier} onChange={(e) => setCourier(e.target.value)} autoComplete="off" />
        <datalist id={`${uid}-couriers`}>
          {couriers.map((c) => <option key={c} value={c} />)}
        </datalist>
      </label>
      <label className={field}>
        Payment date
        <Input type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} />
      </label>
      <label className={field}>
        Amount (PKR)
        <Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
      </label>
      <label className={field}>
        Reference (optional)
        <Input value={reference} onChange={(e) => setReference(e.target.value)} maxLength={100} />
      </label>
      <label className={`${field} sm:col-span-2`}>
        Order numbers this paid for (optional, separated by commas)
        <Input value={orders} onChange={(e) => setOrders(e.target.value)} maxLength={2000} />
      </label>
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2" aria-live="polite">
        <Button type="submit" disabled={busy}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
          Add payment
        </Button>
        {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
        {saved ? (
          <p className="inline-flex items-center gap-1.5 text-sm text-success">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            {saved}
          </p>
        ) : null}
      </div>
    </form>
  );
}
