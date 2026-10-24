"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Play, RotateCcw } from "lucide-react";
import { formatWhen } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { API_MODE, ApiError } from "@/lib/api/config";
import { cancelRun, getRun, listFailedJobs, listRuns, listTasks, markTaskDone, retryJob, runDueJobs, type FailedJob, type Run, type TaskRow } from "@/lib/api/workflows";
import { useLanguage } from "@/lib/i18n";
import { reasonPhrase } from "@/lib/messenger-text";

function why(code: string, t: (s: string) => string, tf: (s: string, p: Record<string, string | number>) => string): string {
  const phrase = reasonPhrase(code);
  return phrase ? tf(phrase.text, phrase.params ?? {}) : t(code);
}

const TONE: Record<string, string> = { done: "bg-success/15 text-success", running: "bg-surface-3 text-ink-2", pending: "bg-surface-3 text-ink-2", failed: "bg-danger/15 text-danger", cancelled: "bg-warning/15 text-warning" };

/** What the workflows did: every run with its steps, steps that failed (with a retry button), and the to-dos workflows made. */
export function WorkflowRunsBoard() {
  const { t } = useLanguage();
  if (API_MODE !== "live") return <p className="text-sm text-muted">{t("Workflow logs are saved in your database. Connect the backend to use them.")}</p>;
  return <RunsContent />;
}

function RunsContent() {
  const { t } = useLanguage();
  const [runs, setRuns] = useState<Omit<Run, "jobs">[] | null>(null);
  const [failedJobs, setFailedJobs] = useState<FailedJob[]>([]);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listRuns(), listFailedJobs(), listTasks()])
      .then(([r, f, k]) => !cancelled && (setRuns(r), setFailedJobs(f), setTasks(k), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  async function runNow() {
    setBusy(true);
    setNote(null);
    try {
      const r = await runDueJobs();
      setNote(`${t("Done")}: ${r.done ?? 0}, ${t("retry later")}: ${r.retry ?? 0}, ${t("failed")}: ${r.failed ?? 0}`);
      reload();
    } catch (e) {
      setNote(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  if (failed) return <ErrorState title={t("Could not load the logs")} description={t("Please check your connection and reload the page.")} />;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" onClick={runNow} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}{t("Run waiting steps now")}</Button>
        <span aria-live="polite" className="text-xs text-muted">{note}</span>
      </div>

      {failedJobs.length > 0 ? (
        <Card>
          <CardHeader><CardTitle>{t("Steps that failed")}</CardTitle><CardDescription>{t("Fix the cause (for example approve the template), then try again.")}</CardDescription></CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">{failedJobs.map((j) => <FailedRow key={j.id} job={j} onChanged={reload} />)}</ul>
          </CardContent>
        </Card>
      ) : null}

      {tasks.length > 0 ? (
        <Card>
          <CardHeader><CardTitle>{t("To-dos and notifications")}</CardTitle></CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {tasks.map((k) => (
                <li key={k.id} className="flex flex-wrap items-center gap-2 text-ink-2">
                  <span className="text-xs text-muted">{k.kind === "task" ? t("To-do") : t("Notification")} · {formatWhen(k.createdAt)}</span> {k.title}
                  <Button variant="ghost" className="ml-auto !px-2.5 !py-1 text-xs" onClick={async () => { await markTaskDone(k.id).catch(() => undefined); reload(); }}>{t("Done")}</Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader><CardTitle>{t("Runs")}</CardTitle><CardDescription>{t("Newest first. Open a run to see each step.")}</CardDescription></CardHeader>
        <CardContent>
          {!runs ? <Skeleton className="h-32 w-full" /> : runs.length === 0 ? <p className="text-sm text-muted">{t("No runs yet.")}</p> : (
            <ul className="space-y-2">{runs.map((r) => <RunRow key={r.id} run={r} onChanged={reload} />)}</ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function FailedRow({ job, onChanged }: { job: FailedJob; onChanged: () => void }) {
  const { t, tf } = useLanguage();
  const [error, setError] = useState<string | null>(null);
  const reason = job.lastError ? why(job.lastError, t, tf) : "";
  return (
    <li className="flex flex-wrap items-center gap-2 text-ink-2">
      <span className="font-medium text-ink">{job.workflowName}</span> · {t("step")} {job.stepIndex + 1} ({job.actionType}) · {reason} · {job.attempts}/{job.maxAttempts}
      <Button variant="secondary" className="ml-auto !px-2.5 !py-1 text-xs" onClick={async () => { try { await retryJob(job.id); onChanged(); } catch (e) { setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again.")); } }}><RotateCcw className="h-3 w-3" aria-hidden="true" />{t("Try again")}</Button>
      {error ? <span role="alert" className="w-full text-xs text-danger">{error}</span> : null}
    </li>
  );
}

function RunRow({ run, onChanged }: { run: Omit<Run, "jobs">; onChanged: () => void }) {
  const { t, tf } = useLanguage();
  const [detail, setDetail] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setDetail(detail ? null : await getRun(run.id).catch(() => null));
  }
  async function stop() {
    try {
      await cancelRun(run.id);
      setDetail(null);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    }
  }

  return (
    <li className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-ink">{run.workflowName}</span> <span className="text-xs text-muted">v{run.workflowVersion} · {formatWhen(run.startedAt)}</span>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${TONE[run.status] ?? TONE.running}`}>{t(run.status)}</span>
        <Button variant="ghost" className="ml-auto !px-2.5 !py-1 text-xs" onClick={toggle}>{detail ? t("Hide steps") : t("Show steps")}</Button>
        {run.status === "running" ? <Button variant="ghost" className="!px-2.5 !py-1 text-xs" onClick={stop}>{t("Stop")}</Button> : null}
      </div>
      {error ? <p role="alert" className="mt-1 text-xs text-danger">{error}</p> : null}
      {detail ? (
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs text-ink-2">
          {detail.jobs.map((j) => (
            <li key={j.id}>
              {j.actionType} · <span className={`rounded-full px-1.5 py-0.5 ${TONE[j.status] ?? ""}`}>{t(j.status)}</span>
              {j.status === "pending" ? ` · ${t("due")} ${formatWhen(j.runAt)}` : ""}
              {j.lastError ? ` · ${why(j.lastError, t, tf)}` : ""}
              {j.result ? ` · ${JSON.stringify(j.result)}` : ""}
            </li>
          ))}
        </ol>
      ) : null}
    </li>
  );
}
