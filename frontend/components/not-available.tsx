const DEFAULT_REASON = "Not available: see the note on this page.";

/** Table-cell marker for a value that cannot be shown yet. */
export function NotAvailableCell({ reason = DEFAULT_REASON }: { reason?: string }) {
  return (
    <span className="text-slate-400" title={reason}>
      —<span className="sr-only">Not available: {reason}</span>
    </span>
  );
}

/** Larger inline note for summary cards. */
export function NotAvailableValue({ reason = DEFAULT_REASON }: { reason?: string }) {
  return (
    <>
      <p className="mt-2 text-lg font-semibold tracking-tight text-slate-400">Not available yet</p>
      <p className="text-xs text-slate-500">{reason}</p>
    </>
  );
}
