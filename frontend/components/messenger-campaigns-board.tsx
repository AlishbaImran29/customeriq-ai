"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Check, Loader2, Plus, Sparkles, Trash2 } from "lucide-react";
import { AiDraftLabel, MessengerGate, Reason, areaClass, fieldClass, formatWhen } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import {
  SEGMENTS, addProduct, approveCampaign, cancelCampaign, deleteCampaign, editCampaign, generateCampaign, getCampaign, listCampaigns, listRecipients,
  previewCampaign, saveCampaignMessages, type Campaign, type CampaignMessages, type CampaignPreview, type Product, type Recipient, type Segment,
} from "@/lib/api/messaging";
import { useLanguage } from "@/lib/i18n";

const STATUS_LABEL: Record<Campaign["status"], string> = { draft: "Draft", approved: "Approved", sending: "Sending", completed: "Completed", cancelled: "Cancelled" };

/**
 * Product announcements. Add a product -> a DRAFT campaign appears. The AI drafts one message per customer segment (you can edit it),
 * you check the audience and 5 sample messages, and only when YOU approve does anything get scheduled. Champions hear first.
 */
export function MessengerCampaignsBoard() {
  return (
    <MessengerGate>
      <CampaignsContent />
    </MessengerGate>
  );
}

function CampaignsContent() {
  const { t } = useLanguage();
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listCampaigns()
      .then((r) => !cancelled && (setCampaigns(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (failed) return <ErrorState title={t("Could not load the campaigns")} description={t("Please check your connection and reload the page.")} />;
  if (openId !== null) return <CampaignDetail id={openId} onBack={() => { setOpenId(null); reload(); }} />;
  return (
    <div className="space-y-5">
      <NewProduct onAdded={(p) => { reload(); if (p.campaignId) setOpenId(p.campaignId); }} />
      {!campaigns ? <Skeleton className="h-40 w-full" /> : campaigns.length === 0 ? <p className="text-sm text-muted">{t("No campaigns yet. Add a product above.")}</p> : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {campaigns.map((c) => (
            <li key={c.id}>
              <Card className="h-full">
                <CardHeader>
                  <CardTitle className="text-base">{c.name}</CardTitle>
                  <CardDescription>{t(STATUS_LABEL[c.status])}{c.counts.total ? ` · ${c.counts.sent}/${c.counts.total}` : ""}</CardDescription>
                </CardHeader>
                <CardContent><Button variant="secondary" onClick={() => setOpenId(c.id)}>{t("Open")}</Button></CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NewProduct({ onAdded }: { onAdded: (p: Product) => void }) {
  const { t } = useLanguage();
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [price, setPrice] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const p = await addProduct({ name: name.trim(), category: category.trim() || undefined, price: price ? Number(price) : undefined, description: description.trim() || undefined });
      setName(""); setCategory(""); setPrice(""); setDescription("");
      onAdded(p);
    } catch (err) {
      setError(err instanceof ApiError ? t(err.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Announce a new product")}</CardTitle>
        <CardDescription>{t("This only makes a draft. Nothing is sent until you approve it. A product from Launch Studio can be announced from its results page.")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2" noValidate>
          <label className={fieldClass}>{t("Product name")}<Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required /></label>
          <label className={fieldClass}>{t("Category")}<Input value={category} onChange={(e) => setCategory(e.target.value)} maxLength={80} /></label>
          <label className={fieldClass}>{t("Price (optional)")}<Input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" /></label>
          <label className={fieldClass}>{t("Short description")}<Input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} /></label>
          <div className="flex items-center gap-3 sm:col-span-2" aria-live="polite">
            <Button type="submit" disabled={busy || !name.trim()}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}{t("Make a draft campaign")}</Button>
            {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function CampaignDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const { t, tf } = useLanguage();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [preview, setPreview] = useState<CampaignPreview | null>(null);
  const [recipients, setRecipients] = useState<Recipient[] | null>(null);
  const [messages, setMessages] = useState<CampaignMessages | null>(null);
  const [offer, setOffer] = useState("");
  const [hours, setHours] = useState("24");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const apply = useCallback(async (c: Campaign) => {
    setCampaign(c);
    setMessages(c.messages);
    setOffer(c.offerText ?? "");
    setHours(String(c.earlyAccessHours));
    setFailed(false);
    if (c.status === "draft") setPreview(await previewCampaign(c.id).catch(() => null));
    else setRecipients(await listRecipients(c.id).catch(() => []));
  }, []);
  const load = useCallback(() => getCampaign(id).then(apply).catch(() => setFailed(true)), [id, apply]);
  useEffect(() => {
    let cancelled = false;
    getCampaign(id)
      .then((c) => { if (!cancelled) void apply(c); })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [id, apply]);

  async function run(label: string, action: () => Promise<string | void>) {
    setBusy(label);
    setError(null);
    setNote(null);
    try {
      const n = await action();
      if (n) setNote(n);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(null);
    }
  }

  if (failed) return <ErrorState title={t("Could not load this campaign")} description={t("Please check your connection and reload the page.")} />;
  if (!campaign) return <Skeleton className="h-64 w-full" />;
  const draft = campaign.status === "draft";
  const toggleSegment = (s: Segment) => {
    const has = campaign.audience.segments.includes(s);
    const segments = has ? campaign.audience.segments.filter((x) => x !== s) : [...campaign.audience.segments, s];
    void run("audience", async () => { await editCampaign(id, { audience: { ...campaign.audience, segments } }); });
  };
  const setMsg = (seg: string, lang: "en" | "ur", value: string) => setMessages((m) => (m ? { ...m, messages: { ...m.messages, [seg]: { ...m.messages[seg], [lang]: value } } } : m));
  const setSubject = (lang: "en" | "ur", value: string) => setMessages((m) => (m ? { ...m, subject: { ...m.subject, [lang]: value } } : m));

  return (
    <div className="space-y-5">
      <Button variant="ghost" onClick={onBack}><ArrowLeft className="h-4 w-4" aria-hidden="true" />{t("Back to campaigns")}</Button>
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">{campaign.name} <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[11px] font-medium text-ink-2">{t(STATUS_LABEL[campaign.status])}</span></CardTitle>
          {campaign.counts.total ? <CardDescription>{tf("{sent} sent, {pending} waiting, {skipped} not sent, {total} in all", campaign.counts)}</CardDescription> : null}
        </CardHeader>
        <CardContent className="space-y-4">
          <fieldset disabled={!draft} className="space-y-3">
            <legend className="text-sm font-medium text-ink">{t("Who should hear about it")}</legend>
            <div className="flex flex-wrap gap-2">
              {SEGMENTS.map((s) => (
                <label key={s} className="flex items-center gap-2 rounded-full border border-line bg-surface-2 px-3 py-1 text-sm text-ink-2">
                  <input type="checkbox" checked={campaign.audience.segments.includes(s)} onChange={() => toggleSegment(s)} className="h-4 w-4 accent-[var(--color-accent)]" />{t(s)}
                </label>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className={fieldClass}>{t("Offer (only if you really have one)")}<Input value={offer} onChange={(e) => setOffer(e.target.value)} maxLength={200} /></label>
              <label className={fieldClass}>{t("Hours Champions hear first")}<Input value={hours} onChange={(e) => setHours(e.target.value)} inputMode="numeric" /></label>
            </div>
            {draft ? <Button variant="secondary" disabled={busy !== null} onClick={() => run("settings", async () => { await editCampaign(id, { offerText: offer.trim(), earlyAccessHours: Math.max(0, Math.min(168, Number(hours) || 0)) }); })}>{t("Save these settings")}</Button> : null}
          </fieldset>

          {draft ? (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <Button onClick={() => run("ai", async () => { await generateCampaign(id, Boolean(messages)); })} disabled={busy !== null}>
                  {busy === "ai" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}{messages ? t("Write again with AI") : t("Write the messages with AI")}
                </Button>
                {campaign.aiDraft ? <AiDraftLabel /> : null}
              </div>
              {messages ? (
                <div className="space-y-3">
                  {Object.entries(messages.messages).map(([seg, m]) => (
                    <div key={seg} className="grid gap-2 rounded-xl border border-line bg-surface-2 p-3 sm:grid-cols-2">
                      <p className="text-sm font-medium text-ink sm:col-span-2">{t(seg)}</p>
                      <label className={fieldClass}>English<textarea className={areaClass} rows={4} value={m.en} onChange={(e) => setMsg(seg, "en", e.target.value)} maxLength={900} /></label>
                      <label className={fieldClass}>اردو<textarea className={areaClass} rows={4} dir="rtl" value={m.ur} onChange={(e) => setMsg(seg, "ur", e.target.value)} maxLength={900} /></label>
                    </div>
                  ))}
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className={fieldClass}>{t("Email subject")} (English)<Input value={messages.subject.en} onChange={(e) => setSubject("en", e.target.value)} maxLength={150} /></label>
                    <label className={fieldClass}>{t("Email subject")} (اردو)<Input dir="rtl" value={messages.subject.ur} onChange={(e) => setSubject("ur", e.target.value)} maxLength={150} /></label>
                  </div>
                  <Button variant="secondary" disabled={busy !== null} onClick={() => run("save", async () => { await saveCampaignMessages(id, messages); return t("Your wording is saved."); })}>{t("Save my wording")}</Button>
                </div>
              ) : <p className="text-sm text-muted">{t("No messages yet. Let the AI write a first draft, then change anything you like.")}</p>}
            </>
          ) : null}
          <div aria-live="polite" className="space-y-1">
            {note ? <p className="text-sm text-success">{note}</p> : null}
            {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
          </div>
        </CardContent>
      </Card>

      {draft && preview ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("Check before you approve")}</CardTitle>
            <CardDescription>{tf("{eligible} customers can be messaged ({noConsent} have not agreed, {noAddress} have no phone or email).", { eligible: preview.audience.eligible, noConsent: preview.audience.noConsent, noAddress: preview.audience.noAddress })}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {preview.audience.truncated ? <p className="text-xs text-warning">{t("The audience is very large, so only the first part is counted here.")}</p> : null}
            <ul className="space-y-2">
              {preview.samples.map((s, i) => (
                <li key={i} className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
                  <p className="text-xs text-muted">{s.customerName} · {t(s.segment)} · {s.channel === "whatsapp" ? "WhatsApp" : t("Email")}</p>
                  {s.error ? <p className="text-warning"><Reason code={s.error} /></p> : <p className="whitespace-pre-wrap text-ink-2" dir="auto">{s.subject ? `${s.subject}\n\n` : ""}{s.text}</p>}
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-3">
              <Button disabled={busy !== null || !messages || preview.audience.eligible === 0} onClick={() => run("approve", async () => { const r = await approveCampaign(id); return tf("Approved: {recipients} customers are scheduled ({early} hear first).", r); })}>
                {busy === "approve" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Check className="h-4 w-4" aria-hidden="true" />}{t("Approve and schedule")}
              </Button>
              <Button variant="ghost" disabled={busy !== null} onClick={() => { if (window.confirm(t("Delete this draft?"))) void run("delete", async () => { await deleteCampaign(id); onBack(); }); }}><Trash2 className="h-4 w-4" aria-hidden="true" />{t("Delete draft")}</Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {!draft ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("Who it goes to")}</CardTitle>
            {campaign.status === "approved" || campaign.status === "sending" ? (
              <CardDescription><Button variant="ghost" disabled={busy !== null} onClick={() => run("cancel", async () => { const r = await cancelCampaign(id); return tf("Stopped. {stopped} waiting messages were cancelled.", r); })}>{t("Stop this campaign")}</Button></CardDescription>
            ) : null}
          </CardHeader>
          <CardContent>
            {!recipients ? <Skeleton className="h-24 w-full" /> : recipients.length === 0 ? <p className="text-sm text-muted">{t("Nobody.")}</p> : (
              <ul className="space-y-1 text-sm text-ink-2">
                {recipients.map((r) => <li key={r.id}>{r.customerName} · {t(r.segment)} · {r.stage === "early" ? t("hears first") : t("hears later")} · {formatWhen(r.scheduledFor)} · {r.status === "sent" ? t("Sent") : r.status === "pending" ? t("Waiting") : <Reason code={r.reason ?? "skipped"} />}</li>)}
              </ul>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
