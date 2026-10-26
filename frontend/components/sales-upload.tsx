"use client";

import { useEffect, useRef, useState } from "react";
import { Download, FlaskConical, Loader2, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/config";
import {
  MAX_SALES_BYTES, deleteDemoSales, getSalesSummary, uploadProductSales,
  type SalesImportResult, type SalesSummary,
} from "@/lib/api/seasons";
import { formatNumber } from "@/lib/utils";
import { fmt } from "@/lib/format";

const linkClass =
  "inline-flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3.5 py-2 text-sm font-medium text-ink-2 hover:bg-surface-3 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60";

/**
 * Import units sold per product (product, date, units). Rows are added up per product per week; uploading
 * a week again replaces it rather than adding to it. Made-up demo sales are labelled and can be deleted here.
 */
export function SalesUpload({ onChange }: { onChange?: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SalesImportResult | null>(null);
  const [summary, setSummary] = useState<SalesSummary | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getSalesSummary()
      .then((s) => !cancelled && setSummary(s))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  async function send(file: File | undefined) {
    if (!file) return;
    setError(null);
    setResult(null);
    if (file.size > MAX_SALES_BYTES) {
      setError("The file is larger than 4 MB. Split it and upload the parts.");
      return;
    }
    setBusy(true);
    try {
      setResult(await uploadProductSales(file));
      setRefresh((k) => k + 1);
      onChange?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function removeDemo() {
    setBusy(true);
    try {
      await deleteDemoSales();
      setConfirming(false);
      setRefresh((k) => k + 1);
      onChange?.();
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 text-sm">
      <p className="text-ink-2">
        Upload how many units of each product you sold: product, date and units. Daily or weekly rows both work. Send the whole history of a week in one file.
      </p>
      <a href="/product_sales_template.csv" download className={linkClass}>
        <Download className="h-4 w-4" aria-hidden="true" />
        CSV template
      </a>
      <div>
        <input ref={input} type="file" accept=".csv,.xlsx" className="sr-only" id="sales-file" onChange={(e) => send(e.target.files?.[0])} />
        <Button disabled={busy} onClick={() => input.current?.click()}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
          Upload product sales
        </Button>
      </div>

      <div aria-live="polite" className="space-y-2">
        {error ? <p role="alert" className="text-danger">{error}</p> : null}
        {result ? (
          <div className="space-y-1 rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-ink-2">
            <p className="text-success">
              <strong>
                {fmt("{products} products: {created} new and {updated} updated weeks. {rejected} rows were rejected.", {
                  products: formatNumber(result.products), created: formatNumber(result.weeksCreated),
                  updated: formatNumber(result.weeksUpdated), rejected: formatNumber(result.rejected),
                })}
              </strong>
            </p>
            {result.errors.slice(0, 5).map((e, i) => (
              <p key={i} className="text-xs">
                Row {e.row ?? "?"}: {e.column ? `${e.column}: ` : ""}
                {e.message}
              </p>
            ))}
          </div>
        ) : null}
      </div>

      {summary && summary.productWeeks > 0 ? (
        <p className="text-xs text-muted">{fmt("{count} product-weeks saved.", { count: formatNumber(summary.productWeeks) })}</p>
      ) : null}

      {summary && summary.demoProductWeeks > 0 ? (
        <div className="space-y-2 rounded-xl border border-warning/30 bg-warning/10 p-3 text-ink-2" role="note">
          <p className="flex items-start gap-2 text-warning">
            <FlaskConical className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>
              <strong>Demo data.</strong>{" "}
              {fmt("{count} of these product-weeks are made up (marked demo (synthetic)). They are not real results.", { count: formatNumber(summary.demoProductWeeks) })}
            </span>
          </p>
          {confirming ? (
            <div className="flex gap-2">
              <Button onClick={removeDemo} disabled={busy} className="bg-danger text-white hover:bg-danger/90">
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                Yes, delete
              </Button>
              <Button variant="secondary" onClick={() => setConfirming(false)} disabled={busy}>Cancel</Button>
            </div>
          ) : (
            <Button variant="secondary" onClick={() => setConfirming(true)}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              Delete demo sales
            </Button>
          )}
        </div>
      ) : null}
    </div>
  );
}
