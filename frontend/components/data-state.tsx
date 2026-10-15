import { redirect, unstable_rethrow } from "next/navigation";
import { Database, FlaskConical, Info } from "lucide-react";
import { RetryButton } from "@/components/retry-button";
import { ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import type { DataMeta, ModelInfo } from "@/lib/types";
import { formatDate, formatNumber } from "@/lib/utils";

export type LoadResult<T> = { ok: true; data: T } | { ok: false; error: ApiError };

/**
 * Run a data loader and turn API failures into a value the page can render as
 * an error state. Next.js internal signals are re-thrown; anything unexpected
 * goes to the route's error boundary. Never substitutes sample data.
 */
export async function load<T>(loader: () => Promise<T>): Promise<LoadResult<T>> {
  try {
    return { ok: true, data: await loader() };
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError) {
      // The session ended (or was never valid): sign in again instead of showing an error.
      if (error.status === 401) redirect("/login?reason=expired");
      return { ok: false, error };
    }
    throw error;
  }
}

/** Says whether the page shows sample data or live data, and as of when. */
export function DataSourceBanner({ meta }: { meta: DataMeta }) {
  if (meta.source === "demo") {
    return (
      <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
        <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>
          <strong>Demo data.</strong> These are realistic sample figures, not your business. No
          backend is configured (<code>NEXT_PUBLIC_API_BASE_URL</code>).
        </p>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
      <Database className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <p>
        <strong>Live data</strong> from your database
        {meta.asOf ? <> · as of {formatDate(meta.asOf)} (latest order)</> : null} ·{" "}
        {formatNumber(meta.customerCount)} customers. Figures are calculated with fixed formulas;
        predictions appear only when a model passed its accuracy test (shown where used).
      </p>
    </div>
  );
}

/** The reason a value is not shown, from the response's `unavailable` list. */
export function reasonFor(meta: DataMeta, field: string): string | undefined {
  return meta.unavailable.find((item) => item.field === field)?.reason;
}

/**
 * Labels model estimates and shows how the model did on data it had not seen.
 * Renders nothing in demo mode or when the model is unavailable.
 */
export function ModelNote({
  model,
  title,
  className,
}: {
  model: ModelInfo;
  title: string;
  className?: string;
}) {
  if (model.status !== "available" || model.metrics.length === 0) return null;
  return (
    <details className={`rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900 ${className ?? ""}`}>
      <summary className="flex cursor-pointer list-none items-center gap-2 font-medium">
        <FlaskConical className="h-4 w-4 shrink-0" aria-hidden="true" />
        {title}: model estimates, not facts. Tested on unseen data. <span className="font-normal underline">Details</span>
      </summary>
      <dl className="mt-2 grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
        {model.metrics.map((metric) => (
          <div key={metric.label} className="flex justify-between gap-3">
            <dt className="text-sky-800">{metric.label}</dt>
            <dd className="font-medium tabular-nums">{metric.value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

/** Shown in live mode when nothing has been imported yet. */
export { NoDataState } from "@/components/no-data-state";

export function DataErrorState({ error }: { error: ApiError }) {
  const hint =
    error.code === "network_error"
      ? "Start the backend (see backend/README.md), then retry."
      : error.status === 503
        ? "The backend could not reach its database."
        : error.code === "not_found"
          ? "The backend does not know this request. It is probably an older version: restart it (or redeploy the API) and retry."
          : undefined;
  return (
    <ErrorState
      title="Couldn't load live data"
      description={hint ? `${error.message} ${hint}` : error.message}
      action={<RetryButton />}
    />
  );
}

// Full class names so Tailwind can find them.
const SKELETON_COLUMNS: Record<number, string> = {
  3: "xl:grid-cols-3",
  4: "xl:grid-cols-4",
  5: "xl:grid-cols-5",
  6: "xl:grid-cols-3",
};

/** Loading placeholder for a page's data section. */
export function PageSkeleton({ cards = 3 }: { cards?: number }) {
  return (
    <div className="space-y-6" role="status" aria-live="polite">
      <span className="sr-only">Loading…</span>
      <Skeleton className="h-10 rounded-xl" />
      <div className={`grid gap-4 sm:grid-cols-2 ${SKELETON_COLUMNS[cards] ?? "xl:grid-cols-3"}`}>
        {Array.from({ length: cards }).map((_, index) => (
          <Skeleton key={index} className="h-28 rounded-2xl" />
        ))}
      </div>
      <Skeleton className="h-80 rounded-2xl" />
      <Skeleton className="h-64 rounded-2xl" />
    </div>
  );
}
