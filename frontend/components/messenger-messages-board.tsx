"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, MessageCircle, Mail, PlayCircle, Send } from "lucide-react";
import { DryRunTag, MessageStatusBadge, MessengerGate, Reason, fieldClass, formatWhen } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import { getSettings, listIncoming, listMessages, processQueue, simulateIncoming, type IncomingRow, type MessageRow, type MessageStatus } from "@/lib/api/messaging";
import { useLanguage } from "@/lib/i18n";

type Show = "all" | MessageStatus;

/**
 * Every message the app tried to send, with what happened to it and WHY a message was not sent. Replies from customers (and STOP)
 * are listed too. In a demo the "pretend a customer replied" box shows how STOP works without WhatsApp.
 */
export function MessengerMessagesBoard() {
  return (
    <MessengerGate>
      <MessagesContent />
    </MessengerGate>
  );
}

function MessagesContent() {
  const { t, tf } = useLanguage();
  const [show, setShow] = useState<Show>("all");
  const [rows, setRows] = useState<MessageRow[] | null>(null);
  const [incoming, setIncoming] = useState<IncomingRow[]>([]);
  const [development, setDevelopment] = useState(false);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [queueNote, setQueueNote] = useState<string | null>(null);

  useEffect(() => {
    getSettings().then((s) => setDevelopment(s.development)).catch(() => undefined);
  }, []);
  useEffect(() => {
    let cancelled = false;
    listMessages(show === "all" ? undefined : show)
      .then((r) => !cancelled && (setRows(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    listIncoming().then((r) => !cancelled && setIncoming(r)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [show, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  async function runQueue() {
    setQueueNote(null);
    try {
      const r = await processQueue();
      setQueueNote(tf("{sent} sent, {requeued} still waiting, {failed} failed, {skipped} not sent.", r));
      reload();
    } catch {
      setQueueNote(t("Something went wrong. Please try again."));
    }
  }

  if (failed) return <ErrorState title={t("Could not load the messages")} description={t("Please check your connection and reload the page.")} />;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <FilterPills
          label={t("Filter by status")} value={show} onChange={setShow}
          options={[
            { value: "all" as Show, label: t("All") }, { value: "sent" as Show, label: t("Sent") }, { value: "queued" as Show, label: t("Waiting") },
            { value: "skipped" as Show, label: t("Not sent") }, { value: "failed" as Show, label: t("Failed") }, { value: "replied" as Show, label: t("Replied") },
          ]}
        />
        <Button variant="secondary" onClick={runQueue}><PlayCircle className="h-4 w-4" aria-hidden="true" />{t("Send waiting messages now")}</Button>
        <span aria-live="polite" className="text-xs text-muted">{queueNote}</span>
      </div>

      {!rows ? <Skeleton className="h-48 w-full" /> : rows.length === 0 ? <p className="text-sm text-muted">{t("No messages yet.")}</p> : (
        <ul className="space-y-3">
          {rows.map((m) => (
            <li key={m.id}>
              <Card>
                <CardContent className="space-y-2 pt-5 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    {m.channel === "whatsapp" ? <MessageCircle className="h-4 w-4 text-accent" aria-label="WhatsApp" /> : <Mail className="h-4 w-4 text-accent" aria-label={t("Email")} />}
                    <span className="font-medium text-ink">{m.customerName}</span>
                    <MessageStatusBadge status={m.status} />
                    <DryRunTag show={m.dryRun} />
                    <span className="text-xs text-muted">{m.category === "utility" ? t("Order update") : t("Marketing")}{m.templateName ? ` · ${m.templateName}` : ""}</span>
                    <span className="ml-auto text-xs text-muted">{formatWhen(m.sentAt ?? m.queuedAt)}</span>
                  </div>
                  {m.subject ? <p className="text-xs text-ink-2"><strong>{t("Subject")}:</strong> {m.subject}</p> : null}
                  {m.text ? <p className="whitespace-pre-wrap rounded-xl border border-line bg-surface-2 p-3 text-ink-2" dir="auto">{m.text}</p> : null}
                  {m.error ? <p className="text-xs text-warning"><Reason code={m.error} /></p> : null}
                  {m.status === "queued" && m.nextAttemptAt ? <p className="text-xs text-muted">{tf("Will be tried at {time}.", { time: formatWhen(m.nextAttemptAt) })}{m.attempts > 0 ? ` (${tf("{n} tries so far", { n: m.attempts })})` : ""}</p> : null}
                  {m.orderId || m.campaignId || m.journeyId ? (
                    <p className="text-xs text-muted">
                      {m.orderId ? t("From an order update") : m.campaignId ? t("From a campaign") : t("From a journey")}
                    </p>
                  ) : null}
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t("What customers sent you")}</CardTitle>
          <CardDescription>{t("Replies from WhatsApp. A reply of STOP (or \"band karo\") switches that customer's WhatsApp messages off at once.")}</CardDescription>
        </CardHeader>
        <CardContent>
          {incoming.length === 0 ? <p className="text-sm text-muted">{t("Nothing yet.")}</p> : (
            <ul className="space-y-2 text-sm">
              {incoming.map((i) => (
                <li key={i.id} className="rounded-xl border border-line bg-surface-2 p-3">
                  <p className="text-xs text-muted">{i.customerName ?? i.fromAddress} · {formatWhen(i.receivedAt)} · {i.messageType}{i.isStop ? ` · ${t("STOP: messages switched off")}` : ""}{i.answer ? ` · ${i.answer === "yes" ? t("answered YES") : t("answered NO")}` : ""}</p>
                  {i.body ? <p className="whitespace-pre-wrap text-ink-2" dir="auto">{i.body}</p> : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {development ? <Simulator onDone={reload} /> : null}
    </div>
  );
}

function Simulator({ onDone }: { onDone: () => void }) {
  const { t } = useLanguage();
  const [phone, setPhone] = useState("");
  const [text, setText] = useState("STOP");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const r = await simulateIncoming(phone.trim(), text);
      setNote(r.stops ? t("STOP received: that customer's WhatsApp messages are now off.") : t("Message received."));
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Demo: pretend a customer replied")}</CardTitle>
        <CardDescription>{t("This runs the same code as the real WhatsApp webhook, without Meta. It is only here while the server is not in production. Try STOP, band karo or بند کرو.")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <label className={fieldClass}>{t("Customer's WhatsApp number")}<Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="0300 1234567" inputMode="tel" /></label>
        <label className={fieldClass}>{t("What they write")}<Input value={text} onChange={(e) => setText(e.target.value)} maxLength={500} dir="auto" /></label>
        <Button onClick={send} disabled={busy || !phone.trim()}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}{t("Send")}</Button>
        <div aria-live="polite" className="sm:col-span-3">
          {note ? <p className="text-sm text-success">{note}</p> : null}
          {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
        </div>
      </CardContent>
    </Card>
  );
}
