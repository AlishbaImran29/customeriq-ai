"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, ShieldCheck, Trash2, Upload } from "lucide-react";
import { ChatOrderCard } from "@/components/chat-order-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Select } from "@/components/ui/input";
import { ApiError } from "@/lib/api/config";
import {
  MAX_CHAT_BYTES, deleteWhatsAppData, getWhatsAppSummary, parseChat, saveAccepted,
  type ChatParse, type DateOrder, type SaveResult, type WhatsAppSummary,
} from "@/lib/api/whatsapp";
import { acceptedRows, counts, rowFrom, type ReviewRow } from "@/lib/chat-review";
import { useLanguage } from "@/lib/i18n";
import { localToday } from "@/lib/quick-order";
import type { FieldErrors } from "@/lib/quick-order";
import { formatNumber } from "@/lib/utils";

type Phase = "idle" | "reading" | "review" | "saving" | "done";

/** The notice shown BEFORE anything is uploaded: what is read, what is saved, and who it is about. */
function PrivacyNotice({ agreed, onAgree }: { agreed: boolean; onAgree: (value: boolean) => void }) {
  const { t } = useLanguage();
  return (
    <div className="rounded-xl border border-info/30 bg-info/10 p-4 text-sm text-ink-2">
      <p className="flex items-center gap-2 font-semibold text-ink">
        <ShieldCheck className="h-5 w-5 text-info" aria-hidden="true" />
        {t("Before you upload a chat")}
      </p>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        <li>{t("Only upload chats with your own customers.")}</li>
        <li>{t("What is read: the messages in the file, to look for amounts, phone numbers, cities and order words.")}</li>
        <li>{t("What is saved: only the orders you accept (name, phone, city, products, amount, payment type, date). The chat itself is never saved.")}</li>
        <li>{t("The file is read in memory on the server and discarded straight away. You can delete everything imported from WhatsApp at any time below.")}</li>
      </ul>
      <label className="mt-3 flex cursor-pointer items-start gap-2 font-medium text-ink">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(event) => onAgree(event.target.checked)}
          className="mt-1 h-4 w-4 accent-accent"
        />
        {t("I will only upload chats with my own customers.")}
      </label>
    </div>
  );
}

/** "Delete all imported WhatsApp data", with a second click to confirm. */
function DeleteWhatsAppData({ refreshKey }: { refreshKey: number }) {
  const { t, tf } = useLanguage();
  const [summary, setSummary] = useState<WhatsAppSummary | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getWhatsAppSummary()
      .then((s) => !cancelled && setSummary(s))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  async function remove() {
    setBusy(true);
    try {
      const result = await deleteWhatsAppData();
      setSummary({ orders: 0, customers: 0 });
      setMessage(tf("Deleted {orders} orders and {customers} customers.", { orders: result.ordersDeleted, customers: result.customersDeleted }));
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Your imported WhatsApp data")}</CardTitle>
        <CardDescription>{t("Orders you accepted from a chat. The chats themselves are never stored.")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-ink-2">
          {summary === null
            ? "…"
            : tf("{orders} orders from {customers} customers were imported from WhatsApp chats.", {
                orders: formatNumber(summary.orders), customers: formatNumber(summary.customers),
              })}
        </p>
        {confirming ? (
          <div className="space-y-2 rounded-xl border border-danger/30 bg-danger/10 p-3 text-sm text-ink-2" role="alert">
            <p>{t("This deletes these orders, and customers who have no other orders. Orders from files or from Add Order are not touched. It cannot be undone.")}</p>
            <div className="flex gap-2">
              <Button onClick={remove} disabled={busy} className="bg-danger text-white hover:bg-danger/90">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Trash2 className="h-4 w-4" aria-hidden="true" />}
                {t("Yes, delete")}
              </Button>
              <Button variant="secondary" onClick={() => setConfirming(false)} disabled={busy}>
                {t("Cancel")}
              </Button>
            </div>
          </div>
        ) : (
          <Button variant="secondary" onClick={() => setConfirming(true)} disabled={!summary || summary.orders === 0}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            {t("Delete all imported WhatsApp data")}
          </Button>
        )}
        <p aria-live="polite" className="text-sm text-success">{message}</p>
      </CardContent>
    </Card>
  );
}

/** Upload a WhatsApp chat, review the suggested orders, and save only the ones accepted. */
export function WhatsAppImport() {
  const { t, tf } = useLanguage();
  const [agreed, setAgreed] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<ChatParse | null>(null);
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [me, setMe] = useState("");
  const [dateOrder, setDateOrder] = useState<DateOrder | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SaveResult | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [today] = useState(() => localToday());
  const input = useRef<HTMLInputElement>(null);

  async function read(chat: File, options: { me?: string; dateOrder?: DateOrder }) {
    setError(null);
    setPhase("reading");
    try {
      const response = await parseChat(chat, options);
      setParsed(response);
      setRows(response.candidates.map(rowFrom));
      setPhase("review");
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
      setPhase(parsed ? "review" : "idle");
    } finally {
      if (input.current) input.current.value = "";
    }
  }

  function choose(chat: File | undefined) {
    if (!chat) return;
    if (chat.size > MAX_CHAT_BYTES) {
      setError(t("This chat is too big (4 MB at most). Export fewer months of the chat and try again."));
      return;
    }
    setFile(chat);
    setMe("");
    setDateOrder(undefined);
    setResult(null);
    void read(chat, {});
  }

  async function save() {
    setError(null);
    setPhase("saving");
    try {
      setResult(await saveAccepted(acceptedRows(rows)));
      setRows([]);
      setPhase("done");
      setRefreshKey((k) => k + 1);
    } catch (e) {
      const problems = e instanceof ApiError ? (e.details as { rows?: Record<string, FieldErrors> } | undefined)?.rows : undefined;
      if (problems) {
        // Put the problems back on the rows they belong to; nothing was saved.
        setRows((current) => {
          const accepted = current.filter((r) => r.status === "accepted");
          return current.map((r) => {
            const index = accepted.indexOf(r);
            return index >= 0 && problems[String(index)] ? { ...r, status: "pending", errors: problems[String(index)] } : r;
          });
        });
        setError(t("Some orders need attention."));
      } else {
        setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
      }
      setPhase("review");
    }
  }

  function reset() {
    setPhase("idle");
    setFile(null);
    setParsed(null);
    setRows([]);
    setResult(null);
    setError(null);
  }

  const c = counts(rows);
  const reviewing = phase === "review" || phase === "saving";

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("Import a WhatsApp chat")}</CardTitle>
          <CardDescription>
            {t("In WhatsApp open the chat, choose Export chat, then Without media, and save the .txt file.")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <PrivacyNotice agreed={agreed} onAgree={setAgreed} />
          <input ref={input} id="chat-file" type="file" accept=".txt,text/plain" className="sr-only" onChange={(event) => choose(event.target.files?.[0])} />
          <Button disabled={!agreed || phase === "reading" || phase === "saving"} onClick={() => input.current?.click()}>
            {phase === "reading" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
            {phase === "reading" ? t("Reading the chat…") : t("Choose chat file (.txt)")}
          </Button>
          {!agreed ? <p className="text-xs text-muted">{t("Tick the box above to choose a file.")}</p> : null}
          <div aria-live="polite">
            {error ? (
              <p role="alert" className="flex items-start gap-2 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                {error}
              </p>
            ) : null}
            {phase === "done" && result ? (
              <div className="flex items-start gap-2 rounded-xl border border-success/30 bg-success/10 px-3 py-3 text-sm text-success">
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
                <div className="space-y-2">
                  <p>
                    <strong>{tf("Saved {saved} orders ({customers} new customers).", { saved: result.saved, customers: result.newCustomers })}</strong>{" "}
                    {result.alreadyImported > 0 ? tf("{count} were already imported before.", { count: result.alreadyImported }) : null}
                  </p>
                  <Button variant="secondary" onClick={reset}>{t("Import another chat")}</Button>
                </div>
              </div>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {reviewing && parsed && file ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("Review the suggested orders")}</CardTitle>
            <CardDescription>
              {tf("Read {messages} messages. Skipped {system} app notices and {media} photos or other media.", {
                messages: formatNumber(parsed.messageCount), system: parsed.systemLines, media: parsed.mediaMessages,
              })}{" "}
              {t("Nothing is saved until you accept it.")}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm font-medium text-ink-2">
                {t("Which name is you (the seller)?")}
                <Select
                  value={me}
                  onChange={(event) => {
                    setMe(event.target.value);
                    void read(file, { me: event.target.value || undefined, dateOrder });
                  }}
                  className="mt-1 h-11 w-full text-base"
                >
                  <option value="">{t("Not sure")}</option>
                  {parsed.senders.map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.name} ({s.messages})
                    </option>
                  ))}
                </Select>
                <span className="mt-1 block text-xs font-normal text-muted">
                  {t("Your own messages are then not counted as order requests. Changing this restarts the review.")}
                </span>
              </label>
              {parsed.dateOrderAmbiguous || dateOrder ? (
                <div>
                  <p className="text-sm font-medium text-ink-2">{t("How are the dates written?")}</p>
                  <div className="mt-1">
                    <FilterPills
                      label={t("How are the dates written?")}
                      options={[
                        { value: "dmy" as const, label: t("Day first (02/03 = 2 March)") },
                        { value: "mdy" as const, label: t("Month first (02/03 = 3 February)") },
                      ]}
                      value={(dateOrder ?? parsed.dateOrder) as "dmy" | "mdy"}
                      onChange={(value) => {
                        setDateOrder(value);
                        void read(file, { me: me || undefined, dateOrder: value });
                      }}
                    />
                  </div>
                  <p className="mt-1 text-xs text-muted">{t("Every date in this chat fits both ways, so please choose.")}</p>
                </div>
              ) : null}
            </div>

            {rows.length === 0 ? (
              <p className="rounded-xl border border-line bg-surface-2/60 px-4 py-6 text-center text-sm text-muted">
                {t("No orders were found in this chat. Orders are recognised by amounts like Rs 2500, phone numbers and words like order, confirm or COD.")}
              </p>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm text-ink-2" aria-live="polite">
                    {tf("{pending} to review · {accepted} accepted · {rejected} rejected", c)}
                  </p>
                  <Button onClick={save} disabled={c.accepted === 0 || phase === "saving"}>
                    {phase === "saving" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <CheckCircle2 className="h-4 w-4" aria-hidden="true" />}
                    {tf("Save {count} accepted orders", { count: c.accepted })}
                  </Button>
                </div>
                {parsed.truncated ? <p className="text-xs text-muted">{t("More possible orders were found than are shown. Save these and import again.")}</p> : null}
                <ul className="space-y-4">
                  {rows.map((row, index) => (
                    <ChatOrderCard
                      key={row.candidate.id}
                      row={row}
                      candidate={parsed.candidates.find((x) => x.id === row.candidate.id) ?? parsed.candidates[index]}
                      today={today}
                      onChange={(next) => setRows((current) => current.map((r) => (r.candidate.id === next.candidate.id ? next : r)))}
                    />
                  ))}
                </ul>
              </>
            )}
          </CardContent>
        </Card>
      ) : null}

      <DeleteWhatsAppData refreshKey={refreshKey} />
    </div>
  );
}
