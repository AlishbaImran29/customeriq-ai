"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Play, Sparkles } from "lucide-react";
import { MessengerGate, fieldClass } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import { editJourney, listJourneys, runJourneysNow, seedJourneys, type Journey } from "@/lib/api/messaging";
import { useLanguage } from "@/lib/i18n";
import { eventLabel, reasonPhrase } from "@/lib/messenger-text";

/**
 * Automatic follow-ups for each customer segment. A share of customers (the holdout) is deliberately NOT messaged, so the Results page
 * can show whether the messages really made a difference. Each journey needs its approved templates before it can be switched on.
 */
export function MessengerJourneysBoard() {
  return (
    <MessengerGate>
      <JourneysContent />
    </MessengerGate>
  );
}

function JourneysContent() {
  const { t, tf } = useLanguage();
  const [journeys, setJourneys] = useState<Journey[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listJourneys()
      .then((r) => !cancelled && (setJourneys(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  async function seed() {
    setBusy("seed");
    setNote(null);
    try {
      const r = await seedJourneys();
      setNote(tf("{journeys} journeys and {templates} templates added.", r));
      reload();
    } catch {
      setNote(t("Something went wrong. Please try again."));
    } finally {
      setBusy(null);
    }
  }
  async function runNow() {
    setBusy("run");
    setNote(null);
    try {
      const r = await runJourneysNow();
      setNote(Object.entries(r).map(([k, v]) => `${k}: ${v}`).join(", ") || t("Nothing was due."));
      reload();
    } catch (e) {
      setNote(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(null);
    }
  }

  if (failed) return <ErrorState title={t("Could not load the journeys")} description={t("Please check your connection and reload the page.")} />;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={seed} disabled={busy !== null}>{busy === "seed" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}{t("Add the standard journeys")}</Button>
        <Button variant="secondary" onClick={runNow} disabled={busy !== null}><Play className="h-4 w-4" aria-hidden="true" />{t("Run journeys now")}</Button>
        <span aria-live="polite" className="text-xs text-muted">{note}</span>
      </div>
      {!journeys ? <Skeleton className="h-48 w-full" /> : journeys.length === 0 ? <p className="text-sm text-muted">{t("No journeys yet. Add the standard ones to begin.")}</p> : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {journeys.map((j) => <JourneyCard key={j.id} journey={j} onChanged={reload} />)}
        </ul>
      )}
    </div>
  );
}

function JourneyCard({ journey, onChanged }: { journey: Journey; onChanged: () => void }) {
  const { t, tf } = useLanguage();
  const [maxPer30, setMaxPer30] = useState(journey.maxPer30Days === null ? "" : String(journey.maxPer30Days));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(patch: Parameters<typeof editJourney>[1]) {
    setBusy(true);
    setError(null);
    try {
      await editJourney(journey.id, patch);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  const stopped = Object.entries(journey.counts.stopped);
  return (
    <li>
      <Card className="h-full">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">{journey.name}
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${journey.enabled ? "bg-success/15 text-success" : "bg-surface-3 text-ink-2"}`}>{journey.enabled ? t("On") : t("Off")}</span>
          </CardTitle>
          {journey.description ? <CardDescription>{journey.description}</CardDescription> : null}
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-ink-2">{t("For segment")}: <strong>{t(journey.triggerSegment)}</strong></p>
          <ol className="space-y-0.5 text-ink-2">
            {journey.steps.map((s, i) => <li key={i}>{tf("Day {day}", { day: s.day })}: {t(eventLabel(s.event))}</li>)}
          </ol>
          <p className="text-xs text-muted">
            {tf("{active} in the journey, {holdout} held back on purpose, {completed} finished, {sent} messages sent.", { active: journey.counts.active, holdout: journey.counts.holdout, completed: journey.counts.completed, sent: journey.messagesSent })}
          </p>
          {stopped.length ? <p className="text-xs text-muted">{t("Stopped early")}: {stopped.map(([k, v]) => `${t(reasonPhrase(k)?.text ?? k)} (${v})`).join(", ")}</p> : null}
          {!journey.templatesReady ? <p className="text-xs text-warning">{t("Some templates for this journey are not approved yet, so it cannot be switched on.")}</p> : null}
          <div className="flex flex-wrap items-end gap-3">
            <label className={fieldClass}>{t("Most messages in 30 days")}<Input value={maxPer30} onChange={(e) => setMaxPer30(e.target.value)} inputMode="numeric" className="w-28" /></label>
            <Button variant="secondary" disabled={busy} onClick={() => save({ maxPer30Days: maxPer30.trim() ? Math.max(1, Number(maxPer30) || 1) : null })}>{t("Save")}</Button>
            <Button disabled={busy || (!journey.enabled && !journey.templatesReady)} variant={journey.enabled ? "ghost" : "primary"} onClick={() => save({ enabled: !journey.enabled })}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}{journey.enabled ? t("Switch off") : t("Switch on")}
            </Button>
          </div>
          <div aria-live="polite">{error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}</div>
        </CardContent>
      </Card>
    </li>
  );
}
