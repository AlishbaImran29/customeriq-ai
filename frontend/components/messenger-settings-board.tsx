"use client";

import { useCallback, useEffect, useState } from "react";
import { CircleCheck, CircleX, Loader2, Mail, MessageCircle, PlayCircle, Save, Send, ShieldCheck } from "lucide-react";
import { MessengerGate, fieldClass } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import { getSettings, runDueNow, saveSettings, testSend, type Channel, type Lang, type MessengerSettings } from "@/lib/api/messaging";
import { useLanguage } from "@/lib/i18n";

/**
 * Connect WhatsApp and email, try a test message, and set the rules every message follows: dry run, quiet hours, the weekly
 * marketing limit. Secrets are never shown or typed here: they live in the server's settings, and this page only says whether
 * each one is set.
 */
export function MessengerSettingsBoard() {
  return (
    <MessengerGate>
      <SettingsContent />
    </MessengerGate>
  );
}

function SettingsContent() {
  const { t } = useLanguage();
  const [settings, setSettings] = useState<MessengerSettings | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    getSettings().then((s) => (setSettings(s), setFailed(false))).catch(() => setFailed(true));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  if (failed) return <ErrorState title={t("Could not load the settings")} description={t("Please check your connection and reload the page.")} />;
  if (!settings) return <Skeleton className="h-64 w-full" />;
  return (
    <div className="space-y-5">
      <DryRunCard settings={settings} onChanged={setSettings} />
      <ConnectionsCard settings={settings} />
      <RulesCard settings={settings} onChanged={setSettings} />
      <TestCard settings={settings} />
      <RunCard />
    </div>
  );
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  const { t } = useLanguage();
  return (
    <li className="flex items-center gap-2 text-sm text-ink-2">
      {ok ? <CircleCheck className="h-4 w-4 text-success" aria-hidden="true" /> : <CircleX className="h-4 w-4 text-muted" aria-hidden="true" />}
      <span>{label}</span>
      <span className="text-xs text-muted">{ok ? t("set") : t("not set")}</span>
    </li>
  );
}

function DryRunCard({ settings, onChanged }: { settings: MessengerSettings; onChanged: (s: MessengerSettings) => void }) {
  const { t } = useLanguage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle(next: boolean) {
    setBusy(true);
    setError(null);
    try {
      onChanged(await saveSettings({ dryRun: next }));
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className={settings.effectiveDryRun ? "border-warning/40" : "border-success/40"}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-accent" aria-hidden="true" />
          {settings.effectiveDryRun ? t("Dry run is ON: nothing is really sent") : t("Dry run is OFF: messages are really sent")}
        </CardTitle>
        <CardDescription>
          {t("In a dry run every message is written to the message log but nobody receives anything. Use it to try the whole feature for free.")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <FilterPills
          label={t("Dry run")}
          value={settings.dryRun ? "on" : "off"}
          onChange={(v) => (busy || settings.dryRunForced ? undefined : toggle(v === "on"))}
          options={[{ value: "on", label: t("Dry run (safe)") }, { value: "off", label: t("Send for real") }]}
        />
        {settings.dryRunForced ? <p className="text-xs text-muted">{t("The server is set to dry run (MESSAGING_DRY_RUN=true), so this cannot be turned off here.")}</p> : null}
        <div aria-live="polite">{error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}</div>
      </CardContent>
    </Card>
  );
}

function ConnectionsCard({ settings }: { settings: MessengerSettings }) {
  const { t } = useLanguage();
  const w = settings.whatsapp.details;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Connections")}</CardTitle>
        <CardDescription>{t("These are set in your server's settings (Vercel), never here. This page only shows whether each one is set.")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5 md:grid-cols-2">
        <div className="space-y-2">
          <p className="flex items-center gap-2 text-sm font-medium text-ink"><MessageCircle className="h-4 w-4 text-accent" aria-hidden="true" />WhatsApp</p>
          <ul className="space-y-1.5">
            <Check ok={w.accessToken} label={t("Access token")} />
            <Check ok={w.phoneNumberId} label={t("Phone number ID")} />
            <Check ok={w.appSecret} label={t("App secret (checks Meta's signature)")} />
            <Check ok={w.verifyToken} label={t("Verify token")} />
          </ul>
          <p className="text-xs text-muted">
            {t("Webhook address to paste into Meta")}: <span className="break-all font-mono text-ink-2">{settings.webhookUrl ?? t("Set PUBLIC_API_URL first")}</span>
          </p>
        </div>
        <div className="space-y-2">
          <p className="flex items-center gap-2 text-sm font-medium text-ink"><Mail className="h-4 w-4 text-accent" aria-hidden="true" />{t("Email")}</p>
          <ul className="space-y-1.5">
            <Check ok={settings.email.configured} label={settings.email.provider ? `${t("Email service")} (${settings.email.provider})` : t("Email service")} />
            <Check ok={settings.unsubscribeReady} label={t("Unsubscribe links (MESSAGING_SECRET and PUBLIC_API_URL)")} />
          </ul>
          <p className="pt-2 text-sm font-medium text-ink">{t("Other")}</p>
          <ul className="space-y-1.5">
            <Check ok={settings.schedulerReady} label={t("Scheduler secret")} />
            <Check ok={settings.shopifyReady} label={t("Shopify webhook secret")} />
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

function RulesCard({ settings, onChanged }: { settings: MessengerSettings; onChanged: (s: MessengerSettings) => void }) {
  const { t } = useLanguage();
  const [quietStart, setQuietStart] = useState(settings.quietStart);
  const [quietEnd, setQuietEnd] = useState(settings.quietEnd);
  const [cap, setCap] = useState(String(settings.weeklyMarketingCap));
  const [language, setLanguage] = useState<Lang>(settings.defaultLanguage);
  const [store, setStore] = useState(settings.storeName ?? "");
  const [review, setReview] = useState(settings.reviewUrl ?? "");
  const [utility, setUtility] = useState(settings.costUtility === null ? "" : String(settings.costUtility));
  const [marketing, setMarketing] = useState(settings.costMarketing === null ? "" : String(settings.costMarketing));
  const [batch, setBatch] = useState(String(settings.campaignBatchSize));
  const [early, setEarly] = useState(String(settings.earlyAccessHours));
  const [holdout, setHoldout] = useState(String(settings.holdoutPercent));
  const [cartFirst, setCartFirst] = useState(String(settings.cartFirstMinutes));
  const [cartSecond, setCartSecond] = useState(String(settings.cartSecondHours));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const money = (text: string) => (text.trim() === "" ? null : Number(text.replace(/,/g, "")));

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    setBusy(true);
    try {
      onChanged(await saveSettings({
        quietStart, quietEnd, weeklyMarketingCap: Number(cap), defaultLanguage: language, storeName: store, reviewUrl: review,
        costUtility: money(utility), costMarketing: money(marketing), campaignBatchSize: Number(batch), earlyAccessHours: Number(early), holdoutPercent: Number(holdout), cartFirstMinutes: Number(cartFirst), cartSecondHours: Number(cartSecond),
      }));
      setSaved(true);
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Please check the numbers and try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Rules every message follows")}</CardTitle>
        <CardDescription>{t("Quiet hours and the weekly limit are checked for every message, so nobody is messaged at night or too often.")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={save} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" noValidate>
          <label className={fieldClass}>{t("Quiet hours start")}<Input type="time" value={quietStart} onChange={(e) => setQuietStart(e.target.value)} /></label>
          <label className={fieldClass}>{t("Quiet hours end")}<Input type="time" value={quietEnd} onChange={(e) => setQuietEnd(e.target.value)} /></label>
          <label className={fieldClass}>{t("Marketing messages per customer per week (0 = none)")}<Input inputMode="numeric" value={cap} onChange={(e) => setCap(e.target.value.replace(/\D/g, ""))} /></label>
          <label className={fieldClass}>{t("Default language")}
            <Select value={language} onChange={(e) => setLanguage(e.target.value as Lang)} className="w-full"><option value="en">English</option><option value="ur">اردو</option></Select>
          </label>
          <label className={fieldClass}>{t("Your shop's name (used in messages)")}<Input value={store} onChange={(e) => setStore(e.target.value)} maxLength={80} /></label>
          <label className={fieldClass}>{t("Review page link")}<Input value={review} onChange={(e) => setReview(e.target.value)} maxLength={300} placeholder="https://" inputMode="url" /></label>
          <label className={fieldClass}>{t("Your price per WhatsApp order update (PKR)")}<Input inputMode="decimal" value={utility} onChange={(e) => setUtility(e.target.value)} /></label>
          <label className={fieldClass}>{t("Your price per WhatsApp marketing message (PKR)")}<Input inputMode="decimal" value={marketing} onChange={(e) => setMarketing(e.target.value)} /></label>
          <label className={fieldClass}>{t("Customers per campaign batch")}<Input inputMode="numeric" value={batch} onChange={(e) => setBatch(e.target.value.replace(/\D/g, ""))} /></label>
          <label className={fieldClass}>{t("Early access for Champions (hours)")}<Input inputMode="numeric" value={early} onChange={(e) => setEarly(e.target.value.replace(/\D/g, ""))} /></label>
          <label className={fieldClass}>{t("Journey holdout (% of customers who get no message)")}<Input inputMode="numeric" value={holdout} onChange={(e) => setHoldout(e.target.value.replace(/\D/g, ""))} /></label>
          <label className={fieldClass}>{t("Abandoned cart: first reminder after (minutes)")}<Input inputMode="numeric" value={cartFirst} onChange={(e) => setCartFirst(e.target.value.replace(/\D/g, ""))} /></label>
          <label className={fieldClass}>{t("Abandoned cart: second reminder after (hours, 0 = none)")}<Input inputMode="numeric" value={cartSecond} onChange={(e) => setCartSecond(e.target.value.replace(/\D/g, ""))} /></label>
          <p className="text-xs text-muted sm:col-span-2 lg:col-span-3">
            {t("Timezone")}: {settings.timezone}. {t("The prices are yours to enter: Meta changes its prices, so none is built in.")}
          </p>
          <div className="flex flex-wrap items-center gap-3 sm:col-span-2 lg:col-span-3" aria-live="polite">
            <Button type="submit" disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}{t("Save settings")}</Button>
            {saved ? <span className="text-sm text-success">{t("Saved.")}</span> : null}
            {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function TestCard({ settings }: { settings: MessengerSettings }) {
  const { t, tf } = useLanguage();
  const [channel, setChannel] = useState<Channel>("whatsapp");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  async function send() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await testSend({ channel, to: phone.trim() || undefined, language: settings.defaultLanguage });
      setResult(r.ok ? tf(r.dryRun ? "Dry run: a test to {to} was written to the log, nothing was sent." : "Test message sent to {to}.", { to: r.sentTo }) : tf("The test could not be sent ({code}).", { code: r.error ?? "?" }));
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Send a test message to yourself")}</CardTitle>
        <CardDescription>{t("A test goes to one address you control. For WhatsApp, Meta's test number only reaches the phones you added in Meta. Email goes to your own login address.")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <FilterPills label={t("Channel")} value={channel} onChange={setChannel} options={[{ value: "whatsapp" as Channel, label: "WhatsApp" }, { value: "email" as Channel, label: t("Email") }]} />
        {channel === "whatsapp" ? (
          <label className={`${fieldClass} block max-w-xs`}>{t("Your WhatsApp number")}<Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="0300 1234567" inputMode="tel" /></label>
        ) : null}
        <Button onClick={send} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}{t("Send test")}</Button>
        <div aria-live="polite">
          {result ? <p className="text-sm text-success">{result}</p> : null}
          {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
        </div>
      </CardContent>
    </Card>
  );
}

function RunCard() {
  const { t, tf } = useLanguage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    setSummary(null);
    try {
      const r = await runDueNow();
      const sent = (r.queue?.sent ?? 0) + (r.campaigns?.sent ?? 0) + (r.journeys?.sent ?? 0) + (r.reviews?.asked ?? 0);
      setSummary(tf("Done. {sent} messages went out or were queued; {stored} customer files were stored.", { sent, stored: r.media?.stored ?? 0 }));
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Run what is due now")}</CardTitle>
        <CardDescription>{t("The scheduler does this every hour by itself. Use the button to try it right away: it sends messages that waited for the end of quiet hours, retries, review requests, campaign batches and journey steps.")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button variant="secondary" onClick={run} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <PlayCircle className="h-4 w-4" aria-hidden="true" />}{t("Run due messages now")}</Button>
        <div aria-live="polite">
          {summary ? <p className="text-sm text-success">{summary}</p> : null}
          {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
        </div>
      </CardContent>
    </Card>
  );
}
