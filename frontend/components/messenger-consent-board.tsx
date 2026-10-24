"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { History, Loader2, Search, ShieldCheck, ShieldOff, Upload } from "lucide-react";
import { ConsentBadge, MessengerGate, fieldClass, formatWhen } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import {
  changeConsent, consentHistory, getSettings, importConsent, listConsent,
  type Channel, type ChannelConsent, type ConsentCustomer, type ConsentImportResult, type ConsentPage, type ConsentState, type MessengerSettings,
} from "@/lib/api/messaging";
import { useLanguage } from "@/lib/i18n";

const SOURCES: Record<string, string> = {
  manual: "You recorded it", import: "File import", add_order: "Ticked when adding an order", shopify: "Shopify checkout box",
  whatsapp_stop: "Customer replied STOP", email_unsubscribe: "Email unsubscribe link", unsubscribe_link: "Unsubscribe link", whatsapp_chat: "WhatsApp chat",
};

/**
 * Who agreed to be messaged, and on which channel (project rule 1: no consent, no message). The seller records what customers
 * told them; a customer who replies STOP or uses an unsubscribe link is switched off automatically and shows as "Stopped".
 */
export function MessengerConsentBoard() {
  return (
    <MessengerGate>
      <ConsentContent />
    </MessengerGate>
  );
}

function ConsentContent() {
  const { t, tf } = useLanguage();
  const [summary, setSummary] = useState<MessengerSettings["consent"] | null>(null);
  const [page, setPage] = useState<ConsentPage | null>(null);
  const [failed, setFailed] = useState(false);
  const [search, setSearch] = useState("");
  const [typed, setTyped] = useState("");
  const [filter, setFilter] = useState<"all" | `${Channel}:${ConsentState}`>("all");
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    getSettings().then((s) => setSummary(s.consent)).catch(() => undefined);
  }, [version]);

  useEffect(() => {
    let cancelled = false;
    const [channel, state] = filter === "all" ? [undefined, undefined] : (filter.split(":") as [Channel, ConsentState]);
    listConsent({ search: search || undefined, channel, state, offset })
      .then((p) => !cancelled && (setPage(p), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [search, filter, offset, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (failed) return <ErrorState title={t("Could not load the customers")} description={t("Please check your connection and reload the page.")} />;
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-accent" aria-hidden="true" />{t("Consent")}</CardTitle>
          <CardDescription>{t("A customer is only messaged on a channel they agreed to. Only record consent when the customer really agreed: this is your proof, and it is kept with the date and the source.")}</CardDescription>
        </CardHeader>
        <CardContent>
          {summary ? (
            <ul className="grid gap-3 sm:grid-cols-2">
              {(["whatsapp", "email"] as Channel[]).map((c) => (
                <li key={c} className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
                  <p className="font-medium text-ink">{c === "whatsapp" ? "WhatsApp" : t("Email")}</p>
                  <p className="text-ink-2">{tf("{a} agreed, {b} stopped, {c} not asked yet", { a: summary[c].optedIn, b: summary[c].optedOut, c: summary[c].notAsked })}</p>
                </li>
              ))}
            </ul>
          ) : <Skeleton className="h-16 w-full" />}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3 pt-5">
          <form onSubmit={(e) => { e.preventDefault(); setOffset(0); setSearch(typed.trim()); }} className="flex flex-col gap-3 sm:flex-row sm:items-end" noValidate>
            <label className={`${fieldClass} flex-1`}>{t("Search by name, phone or email")}<Input value={typed} onChange={(e) => setTyped(e.target.value)} maxLength={80} /></label>
            <Button type="submit" variant="secondary"><Search className="h-4 w-4" aria-hidden="true" />{t("Search")}</Button>
          </form>
          <FilterPills
            label={t("Filter by consent")} value={filter} onChange={(v) => { setOffset(0); setFilter(v); }}
            options={[
              { value: "all" as const, label: t("All customers") },
              { value: "whatsapp:opted_in" as const, label: t("WhatsApp: agreed") },
              { value: "whatsapp:opted_out" as const, label: t("WhatsApp: stopped") },
              { value: "whatsapp:none" as const, label: t("WhatsApp: not asked") },
              { value: "email:opted_in" as const, label: t("Email: agreed") },
              { value: "email:opted_out" as const, label: t("Email: stopped") },
            ]}
          />
        </CardContent>
      </Card>

      {!page ? <Skeleton className="h-48 w-full" /> : page.customers.length === 0 ? <p className="text-sm text-muted">{t("No customers match.")}</p> : (
        <>
          <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {page.customers.map((c) => <CustomerRow key={c.id} customer={c} onChanged={reload} />)}
          </ul>
          <div className="flex items-center justify-between text-sm text-muted">
            <span>{tf("Showing {from} to {to} of {total}", { from: offset + 1, to: offset + page.customers.length, total: page.total })}</span>
            <span className="flex gap-2">
              <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>{t("Previous")}</Button>
              <Button variant="secondary" disabled={offset + 50 >= page.total} onClick={() => setOffset(offset + 50)}>{t("Next")}</Button>
            </span>
          </div>
        </>
      )}

      <ImportCard onDone={reload} />
    </div>
  );
}

function CustomerRow({ customer, onChanged }: { customer: ConsentCustomer; onChanged: () => void }) {
  const { t } = useLanguage();
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Awaited<ReturnType<typeof consentHistory>> | null>(null);

  async function change(channel: Channel, optedIn: boolean) {
    setError(null);
    try {
      await changeConsent(customer.id, { channel, optedIn });
      setHistory(null);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    }
  }

  const line = (channel: Channel, label: string, c: ChannelConsent, address: string | null) => (
    <div className="space-y-1">
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <span className="w-20 shrink-0 font-medium text-ink-2">{label}</span>
        <ConsentBadge state={c.state} />
        <span className="text-xs text-muted">{address ?? t("none on file")}</span>
      </p>
      {c.changedOn ? <p className="pl-[5.5rem] text-xs text-muted">{c.changedOn} · {t(SOURCES[c.source ?? ""] ?? c.source ?? "")}</p> : null}
      <p className="flex flex-wrap gap-2 pl-[5.5rem]">
        {c.state !== "opted_in" ? <Button variant="secondary" onClick={() => change(channel, true)} className="!px-2.5 !py-1 text-xs"><ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />{t("They agreed")}</Button> : null}
        {c.state === "opted_in" ? <Button variant="ghost" onClick={() => change(channel, false)} className="!px-2.5 !py-1 text-xs"><ShieldOff className="h-3.5 w-3.5" aria-hidden="true" />{t("They stopped")}</Button> : null}
      </p>
    </div>
  );

  return (
    <li>
      <Card className="h-full">
        <CardContent className="space-y-2 pt-5">
          <p className="font-medium text-ink">{customer.name}</p>
          {line("whatsapp", "WhatsApp", customer.whatsapp, customer.phone)}
          {line("email", t("Email"), customer.emailConsent, customer.email)}
          <div aria-live="polite">{error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}</div>
          <button type="button" className="inline-flex items-center gap-1 rounded text-xs font-medium text-accent underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
            onClick={async () => setHistory(history ? null : await consentHistory(customer.id).catch(() => []))}>
            <History className="h-3 w-3" aria-hidden="true" />{history ? t("Hide history") : t("Show history")}
          </button>
          {history ? (
            history.length === 0 ? <p className="text-xs text-muted">{t("No changes recorded.")}</p> : (
              <ul className="space-y-1 text-xs text-ink-2">
                {history.map((h, i) => <li key={i}>{formatWhen(h.at)} · {h.channel === "whatsapp" ? "WhatsApp" : t("Email")} · {h.action === "opt_in" ? t("agreed") : t("stopped")} · {t(SOURCES[h.source] ?? h.source)}{h.note ? ` · ${h.note}` : ""}</li>)}
              </ul>
            )
          ) : null}
        </CardContent>
      </Card>
    </li>
  );
}

function ImportCard({ onDone }: { onDone: () => void }) {
  const { t, tf } = useLanguage();
  const input = useRef<HTMLInputElement>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ConsentImportResult | null>(null);

  async function send(file: File | undefined) {
    if (!file) return;
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      setResult(await importConsent(file, confirmed));
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Import consent you collected elsewhere")}</CardTitle>
        <CardDescription>{t("A CSV or Excel file with the columns: phone and/or email, channel (whatsapp or email), opted_in (yes or no), and optionally date and source. Customers that cannot be found are listed, not created.")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <label className="flex items-start gap-2 text-sm text-ink-2">
          <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--color-accent)]" />
          {t("I confirm that these customers really agreed to be messaged.")}
        </label>
        <input ref={input} type="file" accept=".csv,.xlsx" className="sr-only" id="consent-file" onChange={(e) => send(e.target.files?.[0])} />
        <Button disabled={busy || !confirmed} onClick={() => input.current?.click()}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
          {t("Upload consent file")}
        </Button>
        <div aria-live="polite" className="space-y-1">
          {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
          {result ? (
            <>
              <p className="text-sm text-success">{tf("{changed} changed, {unchanged} already the same, {missing} customers not found, {rejected} rows rejected.", { changed: result.changed, unchanged: result.unchanged, missing: result.notFound, rejected: result.rejected })}</p>
              {result.errors.slice(0, 5).map((e, i) => <p key={i} className="text-xs text-ink-2">{t("Row")} {e.row ?? "?"}: {e.column ? `${e.column}: ` : ""}{e.message}</p>)}
            </>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
