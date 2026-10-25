"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, Plus } from "lucide-react";
import Link from "next/link";
import { formatWhen } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { API_MODE, ApiError } from "@/lib/api/config";
import { STAGES, addLead, leadEvents, leadSummary, listLeads, moveLead, type Lead, type LeadEvent, type LeadSummary, type Stage } from "@/lib/api/leads";
import { useLanguage } from "@/lib/i18n";

const field = "flex flex-col gap-1 text-sm font-medium text-ink-2";
const STAGE_LABEL: Record<Stage, string> = { new: "New lead", contacted: "Contacted", interested: "Interested", converted: "Converted", lost: "Lost" };
const SOURCE_LABEL: Record<string, string> = { manual: "Entered by hand", website_form: "Website form", meta_lead_ad: "Meta Lead Ad", click_to_whatsapp: "Click-to-WhatsApp" };

/** Leads from your website form, Meta Lead Ads, Click-to-WhatsApp ads and by hand, moved along New -> Contacted -> Interested -> Converted (or Lost). */
export function LeadsBoard() {
  const { t } = useLanguage();
  if (API_MODE !== "live") return <p className="text-sm text-muted">{t("Leads are saved in your database. Connect the backend to use them.")}</p>;
  return <LeadsContent />;
}

function LeadsContent() {
  const { t, tf } = useLanguage();
  const [show, setShow] = useState<"all" | Stage>("all");
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [summary, setSummary] = useState<LeadSummary | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listLeads(show === "all" ? undefined : show), leadSummary()])
      .then(([l, s]) => !cancelled && (setLeads(l), setSummary(s), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [show, version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (failed) return <ErrorState title={t("Could not load the leads")} description={t("Please check your connection and reload the page.")} />;
  return (
    <div className="space-y-5">
      {summary && summary.overdue > 0 ? (
        <p role="status" className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm text-ink">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
          {tf("{n} new leads have waited more than {h} hours. Contact them first.", { n: summary.overdue, h: summary.slaHours })}
        </p>
      ) : null}
      <NewLead onAdded={reload} />
      <FilterPills
        label={t("Filter by stage")} value={show} onChange={setShow}
        options={[{ value: "all" as const, label: t("All") }, ...STAGES.map((s) => ({ value: s, label: `${t(STAGE_LABEL[s])}${summary ? ` (${summary.stages[s]})` : ""}` }))]}
      />
      {!leads ? <Skeleton className="h-40 w-full" /> : leads.length === 0 ? <p className="text-sm text-muted">{t("No leads here.")}</p> : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">{leads.map((l) => <LeadCard key={l.id} lead={l} onChanged={reload} />)}</ul>
      )}
    </div>
  );
}

function NewLead({ onAdded }: { onAdded: () => void }) {
  const { t } = useLanguage();
  const [v, setV] = useState({ name: "", phone: "", email: "", interest: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await addLead({ name: v.name || undefined, phone: v.phone || undefined, email: v.email || undefined, productInterest: v.interest || undefined });
      setV({ name: "", phone: "", email: "", interest: "" });
      onAdded();
    } catch (err) {
      setError(err instanceof ApiError ? t(err.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle>{t("Add a lead")}</CardTitle><CardDescription>{t("A phone number or an email address is needed.")}</CardDescription></CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4" noValidate>
          <label className={field}>{t("Name")}<Input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} maxLength={120} /></label>
          <label className={field}>{t("Phone")}<Input value={v.phone} onChange={(e) => setV({ ...v, phone: e.target.value })} inputMode="tel" placeholder="0300 1234567" /></label>
          <label className={field}>{t("Email")}<Input value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} maxLength={320} /></label>
          <label className={field}>{t("Interested in")}<Input value={v.interest} onChange={(e) => setV({ ...v, interest: e.target.value })} maxLength={200} /></label>
          <div className="flex items-center gap-3 sm:col-span-4" aria-live="polite">
            <Button type="submit" disabled={busy || (!v.phone.trim() && !v.email.trim())}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}{t("Add lead")}</Button>
            {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function LeadCard({ lead, onChanged }: { lead: Lead; onChanged: () => void }) {
  const { t, tf } = useLanguage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<LeadEvent[] | null>(null);

  async function go(stage: Stage) {
    let extra: { lostReason?: string; followUpInHours?: number } = {};
    if (stage === "lost") {
      const reason = window.prompt(t("Why was this lead lost? (optional)"));
      if (reason === null) return;
      extra = { lostReason: reason };
    } else if (stage === "contacted" || stage === "interested") {
      extra = { followUpInHours: 24 };
    }
    setBusy(true);
    setError(null);
    try {
      await moveLead(lead.id, stage, extra);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li>
      <Card className="h-full">
        <CardContent className="space-y-2 pt-5 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-ink">{lead.name ?? lead.phone ?? lead.email}</span>
            <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[11px] font-medium text-ink-2">{t(STAGE_LABEL[lead.stage])}</span>
            {lead.overdue ? <span className="inline-flex items-center gap-1 rounded-full bg-warning/15 px-2 py-0.5 text-[11px] font-medium text-warning"><AlertTriangle className="h-3 w-3" aria-hidden="true" />{t("Overdue")}</span> : null}
          </div>
          <p className="text-xs text-muted">
            {[lead.phone, lead.email].filter(Boolean).join(" · ")} · {t(SOURCE_LABEL[lead.source] ?? lead.source)}{lead.campaign ? ` · ${lead.campaign}` : ""}{lead.utmSource ? ` · utm: ${lead.utmSource}` : ""} · {formatWhen(lead.createdAt)}
          </p>
          {lead.productInterest ? <p className="text-ink-2">{t("Interested in")}: {lead.productInterest}</p> : null}
          {lead.lostReason ? <p className="text-xs text-muted">{t("Lost because")}: {lead.lostReason}</p> : null}
          {lead.followUpAt ? <p className="text-xs text-muted">{tf("Follow up by {time}", { time: formatWhen(lead.followUpAt) })}</p> : null}
          <div className="flex flex-wrap items-center gap-2">
            {lead.allowedNext.map((s) => (
              <Button key={s} variant={s === "converted" ? "primary" : "secondary"} disabled={busy} onClick={() => go(s)} className="!px-2.5 !py-1 text-xs">{s === "new" ? t("Reopen") : t(`Move to: ${STAGE_LABEL[s]}`)}</Button>
            ))}
            {lead.customerId ? <Link href="/segmentation" className="text-xs font-medium text-accent underline underline-offset-2">{t("See customers")}</Link> : null}
            <button type="button" className="text-xs font-medium text-accent underline underline-offset-2" onClick={async () => setEvents(events ? null : await leadEvents(lead.id).catch(() => []))}>{events ? t("Hide history") : t("Show history")}</button>
          </div>
          {events ? <ul className="space-y-1 text-xs text-ink-2">{events.map((e, i) => <li key={i}>{formatWhen(e.at)} · {e.event}{e.detail.to ? `: ${String(e.detail.frm)} → ${String(e.detail.to)}` : ""}</li>)}</ul> : null}
          <div aria-live="polite">{error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}</div>
        </CardContent>
      </Card>
    </li>
  );
}
