"use client";

import { useEffect, useRef, useState } from "react";
import { Download, FlaskConical, Loader2, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/config";
import {
  MAX_PAYMENT_BYTES, deleteDemoPayments, getPaymentsSummary, uploadPayments,
  type PaymentImportResult, type PaymentsSummary,
} from "@/lib/api/cash";
import { formatNumber } from "@/lib/utils";
import { fmt } from "@/lib/format";

const linkClass =
  "inline-flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3.5 py-2 text-sm font-medium text-ink-2 hover:bg-surface-3 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60";

/**
 * Import the payments couriers made to the seller (courier, date, amount). Uploading the same sheet again
 * does not count the money twice. Made-up demo payments are always labelled and can be deleted here.
 */
export function PaymentUpload({ onChange }: { onChange?: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PaymentImportResult | null>(null);
  const [summary, setSummary] = useState<PaymentsSummary | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getPaymentsSummary()
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
    if (file.size > MAX_PAYMENT_BYTES) {
      setError("The file is larger than 4 MB. Split it and upload the parts.");
      return;
    }
    setBusy(true);
    try {
      setResult(await uploadPayments(file));
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
      await deleteDemoPayments();
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
        Upload the payments couriers sent you: courier, payment date and amount. You can also name the orders a payment was for.
      </p>
      <a href="/payments_template.csv" download className={linkClass}>
        <Download className="h-4 w-4" aria-hidden="true" />
        CSV template
      </a>
      <div>
        <input ref={input} type="file" accept=".csv,.xlsx" className="sr-only" id="payments-file" onChange={(e) => send(e.target.files?.[0])} />
        <Button disabled={busy} onClick={() => input.current?.click()}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
          Upload payments
        </Button>
      </div>

      <div aria-live="polite" className="space-y-2">
        {error ? <p role="alert" className="text-danger">{error}</p> : null}
        {result ? (
          <div className="space-y-1 rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-ink-2">
            <p className="text-success">
              <strong>
                {fmt("{created} new and {updated} updated payments. {rejected} rows were rejected.", {
                  created: formatNumber(result.created), updated: formatNumber(result.updated), rejected: formatNumber(result.rejected),
                })}
              </strong>
            </p>
            {result.newCourierNames.length > 0 ? (
              <p>
                {fmt("New courier names (not in the list, kept as typed): {names}. If one is just another spelling of a courier you know, add it to backend/app/data/courier_names.json.", {
                  names: result.newCourierNames.join(", "),
                })}
              </p>
            ) : null}
            {result.errors.slice(0, 5).map((e, i) => (
              <p key={i} className="text-xs">
                Row {e.row ?? "?"}: {e.column ? `${e.column}: ` : ""}
                {e.message}
              </p>
            ))}
          </div>
        ) : null}
      </div>

      {summary && summary.payments > 0 ? (
        <p className="text-xs text-muted">{fmt("{count} payments saved.", { count: formatNumber(summary.payments) })}</p>
      ) : null}

      {summary && summary.demoPayments > 0 ? (
        <div className="space-y-2 rounded-xl border border-warning/30 bg-warning/10 p-3 text-ink-2" role="note">
          <p className="flex items-start gap-2 text-warning">
            <FlaskConical className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>
              <strong>Demo data.</strong>{" "}
              {fmt("{count} of these payments are made up (marked demo (synthetic)). They are not real results.", { count: formatNumber(summary.demoPayments) })}
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
              Delete demo payments
            </Button>
          )}
        </div>
      ) : null}
    </div>
  );
}
