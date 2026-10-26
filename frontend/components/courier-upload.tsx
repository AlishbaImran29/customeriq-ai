"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Loader2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/config";
import { MAX_IMPORT_BYTES, uploadCourierFile, type CourierImportResult } from "@/lib/api/data-import";
import { fmt } from "@/lib/format";

/**
 * Add the real delivery results from the courier (order_id, customer_id, status, date). They replace
 * the cancellation stand-in labels, so the model learns from what really happened.
 */
export function CourierUpload() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CourierImportResult | null>(null);

  async function send(file: File | undefined) {
    if (!file) return;
    setError(null);
    setResult(null);
    if (file.size > MAX_IMPORT_BYTES) {
      setError("The file is larger than 10 MB.");
      return;
    }
    setBusy(true);
    try {
      setResult(await uploadCourierFile(file));
      router.refresh(); // the model is retrained on the new labels
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-2">
        Upload a CSV or Excel file from your courier with these columns:{" "}
        <code className="text-xs">order_id, customer_id, status, date</code>.{" "}
        Status is delivered or returned. The orders must already be imported.
      </p>
      <p className="text-sm">
        <a href="/courier_results_template.csv" download className="font-medium text-accent hover:underline">
          Download the template
        </a>{" "}
        <span className="text-muted">The two example rows only show the format. Replace them with your own.</span>
      </p>
      <input
        ref={input}
        type="file"
        accept=".csv,.xlsx"
        className="sr-only"
        id="courier-file"
        onChange={(event) => send(event.target.files?.[0])}
      />
      <Button variant="secondary" disabled={busy} onClick={() => input.current?.click()}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
        Upload courier results
      </Button>
      <div aria-live="polite">
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        {result ? (
          <div className="rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
            <p>
              {fmt("{updated} orders updated ({returned} returned). {rejected} rows were rejected.", {
                updated: result.rowsUpdated,
                returned: result.rowsReturned,
                rejected: result.rowsRejected,
              })}
            </p>
            {result.errors.slice(0, 5).map((e, i) => (
              <p key={i} className="text-xs text-ink-2">
                Row {e.row ?? "?"}: {e.column ? `${e.column}: ` : ""}
                {e.message}
              </p>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
