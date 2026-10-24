"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp, Loader2, Plus } from "lucide-react";
import { Money } from "@/components/money";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { API_MODE, ApiError } from "@/lib/api/config";
import { addStockItem, adjustStock, changeStockItem, listStock, stockMovements, type StockItem, type StockMovement } from "@/lib/api/inventory";
import { useLanguage } from "@/lib/i18n";
import { formatDate } from "@/lib/utils";

const field = "flex flex-col gap-1 text-sm font-medium text-ink-2";

const KIND_LABEL: Record<string, string> = { receive: "Goods received", adjustment: "Correction", reserve: "Reserved for an order", release: "Reservation given back", sale: "Sold", return: "Returned to shelf" };

/**
 * Simple inventory. An order that is Confirmed reserves its items, Dispatched sells them; you give a cancelled order's reservation
 * back and restock a returned one yourself. Orders are matched to items by SKU or name. Every change is listed, nothing is overwritten.
 */
export function InventoryBoard() {
  const { t } = useLanguage();
  if (API_MODE !== "live") return <p className="text-sm text-muted">{t("Inventory is saved in your database. Connect the backend to use it.")}</p>;
  return <InventoryContent />;
}

function InventoryContent() {
  const { t, tf } = useLanguage();
  const [items, setItems] = useState<StockItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listStock()
      .then((r) => !cancelled && (setItems(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (failed) return <ErrorState title={t("Could not load the stock")} description={t("Please check your connection and reload the page.")} />;
  const low = items?.filter((i) => i.low && i.status === "active") ?? [];
  return (
    <div className="space-y-5">
      {low.length > 0 ? (
        <p role="status" className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm text-ink">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
          {tf("{n} items are low or sold out: {names}", { n: low.length, names: low.slice(0, 5).map((i) => i.name).join(", ") })}
        </p>
      ) : null}
      <NewItem onAdded={reload} />
      {!items ? <Skeleton className="h-48 w-full" /> : items.length === 0 ? <p className="text-sm text-muted">{t("No stock items yet. Add your first product above.")}</p> : (
        <ul className="space-y-3">{items.map((i) => <ItemCard key={i.id} item={i} onChanged={reload} />)}</ul>
      )}
    </div>
  );
}

function NewItem({ onAdded }: { onAdded: () => void }) {
  const { t } = useLanguage();
  const [v, setV] = useState({ sku: "", name: "", stock: "", threshold: "", cost: "", price: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const num = (s: string) => (s.trim() === "" ? undefined : Number(s));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await addStockItem({ sku: v.sku.trim(), name: v.name.trim(), stock: num(v.stock), reorderThreshold: num(v.threshold), costPrice: num(v.cost), sellingPrice: num(v.price) });
      setV({ sku: "", name: "", stock: "", threshold: "", cost: "", price: "" });
      onAdded();
    } catch (err) {
      setError(err instanceof ApiError ? t(err.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Add a stock item")}</CardTitle>
        <CardDescription>{t("Use the same name or SKU you write in orders, so orders can find the item.")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3" noValidate>
          <label className={field}>SKU<Input value={v.sku} onChange={(e) => setV({ ...v, sku: e.target.value })} maxLength={40} required /></label>
          <label className={`${field} sm:col-span-2`}>{t("Name")}<Input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} maxLength={160} required /></label>
          <label className={field}>{t("Units on the shelf")}<Input value={v.stock} onChange={(e) => setV({ ...v, stock: e.target.value })} inputMode="numeric" /></label>
          <label className={field}>{t("Warn me at or below")}<Input value={v.threshold} onChange={(e) => setV({ ...v, threshold: e.target.value })} inputMode="numeric" /></label>
          <label className={field}>{t("Cost price")}<Input value={v.cost} onChange={(e) => setV({ ...v, cost: e.target.value })} inputMode="decimal" /></label>
          <label className={field}>{t("Selling price")}<Input value={v.price} onChange={(e) => setV({ ...v, price: e.target.value })} inputMode="decimal" /></label>
          <div className="flex items-center gap-3 sm:col-span-3" aria-live="polite">
            <Button type="submit" disabled={busy || !v.sku.trim() || !v.name.trim()}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}{t("Add item")}</Button>
            {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function ItemCard({ item, onChanged }: { item: StockItem; onChanged: () => void }) {
  const { t, tf } = useLanguage();
  const [delta, setDelta] = useState("");
  const [kind, setKind] = useState<"receive" | "adjustment">("receive");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [moves, setMoves] = useState<StockMovement[] | null>(null);

  async function apply() {
    setBusy(true);
    setError(null);
    try {
      const n = Math.trunc(Number(delta));
      await adjustStock(item.id, kind === "receive" ? Math.abs(n) : n, kind, note.trim() || undefined);
      setDelta("");
      setNote("");
      setMoves(null);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? t(err.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li>
      <Card className={item.status === "archived" ? "opacity-70" : undefined}>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">
            {item.name} <span className="text-xs font-normal text-muted">{item.sku}</span>
            {item.low && item.status === "active" ? <span className="inline-flex items-center gap-1 rounded-full bg-warning/15 px-2 py-0.5 text-[11px] font-medium text-warning"><AlertTriangle className="h-3 w-3" aria-hidden="true" />{item.available <= 0 ? t("Sold out") : t("Low stock")}</span> : null}
            {item.status === "archived" ? <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[11px] font-medium text-ink-2">{t("Archived")}</span> : null}
          </CardTitle>
          <CardDescription>
            {tf("{stock} on the shelf, {reserved} reserved, {available} available", { stock: item.stock, reserved: item.reserved, available: item.available })}
            {item.sellingPrice !== null ? <> · <Money value={item.sellingPrice} /></> : null}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-4">
            <label className={field}>{t("Change")}
              <select value={kind} onChange={(e) => setKind(e.target.value as "receive" | "adjustment")} className="h-10 rounded-xl border border-line bg-surface px-3 text-sm text-ink">
                <option value="receive">{t("Goods received (+)")}</option>
                <option value="adjustment">{t("Correct the count (+ or -)")}</option>
              </select>
            </label>
            <label className={field}>{t("Units")}<Input value={delta} onChange={(e) => setDelta(e.target.value)} inputMode="numeric" /></label>
            <label className={`${field} sm:col-span-2`}>{t("Note (optional)")}<Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} /></label>
          </div>
          <div className="flex flex-wrap items-center gap-3" aria-live="polite">
            <Button onClick={apply} disabled={busy || !delta.trim() || !Number.isFinite(Number(delta)) || Math.trunc(Number(delta)) === 0}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}{t("Save")}</Button>
            <Button variant="ghost" onClick={async () => { await changeStockItem(item.id, { status: item.status === "active" ? "archived" : "active" }).catch(() => undefined); onChanged(); }}>{item.status === "active" ? t("Archive") : t("Restore")}</Button>
            <button type="button" onClick={async () => setMoves(moves ? null : await stockMovements(item.id).catch(() => []))} className="inline-flex items-center gap-1 rounded text-xs font-medium text-accent underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40">
              {moves ? <ChevronUp className="h-3 w-3" aria-hidden="true" /> : <ChevronDown className="h-3 w-3" aria-hidden="true" />}{moves ? t("Hide history") : t("Show history")}
            </button>
            {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
          </div>
          {moves ? (
            moves.length === 0 ? <p className="text-xs text-muted">{t("No changes yet.")}</p> : (
              <ul className="space-y-1 text-xs text-ink-2">
                {moves.map((m) => <li key={m.id}>{formatDate(m.at)} · {t(KIND_LABEL[m.kind] ?? m.kind)} · {m.quantity}{m.orderId ? ` · ${t("order")} #${m.orderId}` : ""}{m.note ? ` · ${m.note}` : ""}</li>)}
              </ul>
            )
          ) : null}
        </CardContent>
      </Card>
    </li>
  );
}
