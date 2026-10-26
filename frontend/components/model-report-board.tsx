"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, EyeOff } from "lucide-react";
import { ErrorState } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { API_MODE } from "@/lib/api/config";
import { beatsBaseline, getModelReport, scoreText, type ModelReport, type ReportRow } from "@/lib/api/model-report";
import { formatDate } from "@/lib/utils";
import { fmt } from "@/lib/format";

/**
 * Model Report Card: every model next to its simple baseline, on data it did not train on, and the trust rule's decision.
 * A model that does not beat its baseline is Hidden everywhere in the app, and the reason is kept here.
 */
export function ModelReportBoard() {
  // The report is built by the backend, so it needs live mode.
  if (API_MODE !== "live") return <DemoNote />;
  return <ReportContent />;
}

function ReportContent() {
  const [report, setReport] = useState<ModelReport | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getModelReport()
      .then((r) => !cancelled && setReport(r))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  if (failed) return <ErrorState title="Could not load the model report" description="Please check your connection and reload the page." />;
  if (!report) return <Skeleton className="h-64 w-full" />;
  return (
    <div className="space-y-5">
      <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {report.rows.map((row) => <ModelCard key={row.model} row={row} />)}
      </ul>
      <Card>
        <CardHeader>
          <CardTitle>History of decisions</CardTitle>
          <CardDescription>{"A line is added only when a model's decision or score changes, for example after a new import."}</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1 text-sm text-ink-2">
            {report.history.map((h, i) => (
              <li key={i}>
                {formatDate(h.createdAt)} · {h.label} · {h.decision === "shown" ? "Shown" : "Hidden"}
                {h.modelScore !== null ? ` · ${scoreText(h.modelScore)} vs ${scoreText(h.baselineScore)}` : ""}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function ModelCard({ row }: { row: ReportRow }) {
  const shown = row.decision === "shown";
  const beats = beatsBaseline(row);
  return (
    <li>
      <Card className="h-full">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">
            {row.label}
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${shown ? "bg-success/15 text-success" : "bg-surface-3 text-ink-2"}`}>
              {shown ? <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> : <EyeOff className="h-3 w-3" aria-hidden="true" />}
              {shown ? "Shown" : "Hidden"}
            </span>
          </CardTitle>
          {row.metric ? <CardDescription>Metric: {row.metric} ({row.higherIsBetter ? "higher is better" : "lower is better"})</CardDescription> : null}
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {row.modelScore !== null ? (
            <dl className="grid grid-cols-2 gap-3">
              <div><dt className="text-xs text-muted">Model score</dt><dd className="text-lg font-semibold text-ink">{scoreText(row.modelScore)}</dd></div>
              <div><dt className="text-xs text-muted">Baseline score</dt><dd className="text-lg font-semibold text-ink">{scoreText(row.baselineScore)}</dd></div>
            </dl>
          ) : <p className="text-muted">No test score yet.</p>}
          {beats !== null ? <p className={beats ? "text-success" : "text-warning"}>{beats ? "Beats the baseline." : "Does not beat the baseline."}</p> : null}
          {row.testSize !== null ? <p className="text-xs text-muted">{fmt("Tested on {n} cases", { n: row.testSize })}{row.splitDate ? ` · ${"test period starts"} ${formatDate(row.splitDate)}` : ""}</p> : null}
          {row.reason ? <p className="text-ink-2">{row.reason}</p> : null}
        </CardContent>
      </Card>
    </li>
  );
}

function DemoNote() {
  return <p className="text-sm text-muted">The Model Report Card is built from your database. Connect the backend to see it.</p>;
}
