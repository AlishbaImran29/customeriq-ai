"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, PlayCircle, Trash2 } from "lucide-react";
import { MessengerGate, formatWhen } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import { deleteMedia, listMedia, processMedia, setMediaUsable, type MediaFilter, type MediaRow } from "@/lib/api/messaging";
import { useLanguage } from "@/lib/i18n";

/**
 * Photos and videos customers sent after delivery. A file is only usable in ads when the customer answered YES to
 * "may we use this?" and the seller then ticks it. A NO answer means it is never usable (the database refuses it too).
 */
export function MessengerVideosBoard() {
  return (
    <MessengerGate>
      <VideosContent />
    </MessengerGate>
  );
}

function VideosContent() {
  const { t, tf } = useLanguage();
  const [show, setShow] = useState<MediaFilter>("all");
  const [rows, setRows] = useState<MediaRow[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listMedia(show)
      .then((r) => !cancelled && (setRows(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [show, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  async function process() {
    setNote(null);
    try {
      const r = await processMedia();
      setNote(tf("{stored} saved, {rejected} refused, {failed} failed, {waiting} still waiting.", r));
      reload();
    } catch {
      setNote(t("Something went wrong. Please try again."));
    }
  }

  if (failed) return <ErrorState title={t("Could not load the customer videos")} description={t("Please check your connection and reload the page.")} />;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <FilterPills
          label={t("Filter videos")} value={show} onChange={setShow}
          options={[
            { value: "all" as MediaFilter, label: t("All") }, { value: "waiting" as MediaFilter, label: t("Waiting for an answer") },
            { value: "yes" as MediaFilter, label: t("Said yes") }, { value: "no" as MediaFilter, label: t("Said no") },
            { value: "usable" as MediaFilter, label: t("Marked usable") }, { value: "rejected" as MediaFilter, label: t("Refused") },
          ]}
        />
        <Button variant="secondary" onClick={process}><PlayCircle className="h-4 w-4" aria-hidden="true" />{t("Fetch new files now")}</Button>
        <span aria-live="polite" className="text-xs text-muted">{note}</span>
      </div>
      {!rows ? <Skeleton className="h-48 w-full" /> : rows.length === 0 ? <p className="text-sm text-muted">{t("No customer photos or videos yet.")}</p> : (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {rows.map((m) => <MediaCard key={m.id} media={m} onChanged={reload} />)}
        </ul>
      )}
    </div>
  );
}

function MediaCard({ media, onChanged }: { media: MediaRow; onChanged: () => void }) {
  const { t, tf } = useLanguage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  const answer = media.shareAnswer === "yes" ? t("Customer said YES: you may use it") : media.shareAnswer === "no" ? t("Customer said NO: do not use it") : t("Customer has not answered yet");
  return (
    <li>
      <Card className="h-full">
        <CardContent className="space-y-3 pt-5 text-sm">
          {media.url && media.status === "stored" ? (
            media.kind === "video"
              ? <video src={media.url} controls preload="metadata" className="max-h-64 w-full rounded-xl bg-surface-3" />
              // eslint-disable-next-line @next/next/no-img-element
              : <img src={media.url} alt={tf("Photo from {name}", { name: media.customerName })} className="max-h-64 w-full rounded-xl bg-surface-3 object-contain" />
          ) : <p className="rounded-xl bg-surface-3 p-6 text-center text-xs text-muted">{media.status === "pending" ? t("Not saved yet") : media.status === "rejected" ? t("Refused") : t("Could not be saved")}</p>}
          <p className="text-ink"><strong>{media.customerName}</strong>{media.orderNumber ? ` · ${media.orderNumber}` : ""} · {formatWhen(media.receivedAt)}</p>
          {media.error ? <p className="text-xs text-warning">{media.error}</p> : null}
          <p className={media.shareAnswer === "yes" ? "text-success" : media.shareAnswer === "no" ? "text-danger" : "text-muted"}>{answer}</p>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-ink-2">
              <input
                type="checkbox" checked={media.usableInAds} disabled={busy || media.shareAnswer !== "yes" || media.status !== "stored"}
                onChange={(e) => run(() => setMediaUsable(media.id, e.target.checked))} className="h-4 w-4 accent-[var(--color-accent)]"
              />
              {t("Usable in ads")}
            </label>
            <Button variant="ghost" disabled={busy} onClick={() => { if (window.confirm(t("Delete this file for good?"))) void run(() => deleteMedia(media.id)); }} className="ml-auto !px-2.5 !py-1 text-xs">
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />}{t("Delete")}
            </Button>
          </div>
          <div aria-live="polite">{error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}</div>
        </CardContent>
      </Card>
    </li>
  );
}
