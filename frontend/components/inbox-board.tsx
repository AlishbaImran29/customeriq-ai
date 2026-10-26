"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Loader2, Send, UserRound } from "lucide-react";
import { MessengerGate, formatWhen } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import { addFaq, addNote, assignConversation, getThread, listConversations, listFaq, responseMetrics, sendReply, type Conversation, type Faq, type Thread } from "@/lib/api/inbox";
import { fmt } from "@/lib/format";

const INTENT: Record<string, string> = { order_status: "Order status", product_question: "Product question", complaint: "Complaint", return: "Return", refund: "Refund", dispute: "Dispute", other: "Other" };
const NEEDS_PERSON = new Set(["complaint", "return", "refund", "dispute"]);
const field = "flex flex-col gap-1 text-sm font-medium text-ink-2";

/** WhatsApp conversations in one place. A reply is drafted only from your own records and you press send; complaints, returns and refunds are left to a person. */
export function InboxBoard() {
  return (
    <MessengerGate>
      <InboxContent />
    </MessengerGate>
  );
}

function InboxContent() {
  const [rows, setRows] = useState<Conversation[] | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [average, setAverage] = useState<{ minutes: number | null; n: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    listConversations()
      .then((r) => !cancelled && (setRows(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    responseMetrics().then((m) => !cancelled && setAverage({ minutes: m.averageResponseMinutes, n: m.questionsMeasured })).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (failed) return <ErrorState title="Could not load the inbox" description="Please check your connection and reload the page." />;
  if (open !== null) return <ThreadView id={open} onBack={() => { setOpen(null); reload(); }} />;
  return (
    <div className="space-y-5">
      <p className="text-sm text-ink-2">{average?.minutes != null ? fmt("You answer in about {m} minutes on average ({n} questions, last 30 days).", { m: average.minutes, n: average.n }) : fmt("Not enough data yet for an average reply time ({n} questions so far).", { n: average?.n ?? 0 })}</p>
      {!rows ? <Skeleton className="h-40 w-full" /> : rows.length === 0 ? <p className="text-sm text-muted">No customer messages yet.</p> : (
        <ul className="space-y-2">
          {rows.map((c) => (
            <li key={c.customerId}>
              <button type="button" onClick={() => setOpen(c.customerId)} className="w-full rounded-xl border border-line bg-surface-2 p-3 text-left text-sm transition hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40">
                <span className="flex flex-wrap items-center gap-2">
                  <UserRound className="h-4 w-4 text-accent" aria-hidden="true" /><span className="font-medium text-ink">{c.customerName}</span>
                  {c.unread > 0 ? <span className="rounded-full bg-accent px-2 py-0.5 text-[11px] font-semibold text-white">{c.unread}</span> : null}
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${NEEDS_PERSON.has(c.intent) ? "bg-warning/15 text-warning" : "bg-surface-3 text-ink-2"}`}>{(INTENT[c.intent] ?? c.intent)}</span>
                  {c.status === "closed" ? <span className="text-[11px] text-muted">Closed</span> : null}
                  <span className="ml-auto text-xs text-muted">{formatWhen(c.lastAt)}</span>
                </span>
                <span className="mt-1 block truncate text-ink-2" dir="auto">{c.lastText}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <FaqCard />
    </div>
  );
}

function ThreadView({ id, onBack }: { id: number; onBack: () => void }) {
  const [thread, setThread] = useState<Thread | null>(null);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [owner, setOwner] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getThread(id).then((r) => { if (!cancelled) { setThread(r); setOwner(r.assignedTo ?? ""); } }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [id, version]);

  async function run(work: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await work();
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!thread) return <Skeleton className="h-64 w-full" />;
  const s = thread.suggestion;
  return (
    <div className="space-y-4">
      <Button variant="ghost" onClick={onBack}><ArrowLeft className="h-4 w-4" aria-hidden="true" />Back to the inbox</Button>
      <Card>
        <CardHeader><CardTitle>{thread.customerName}</CardTitle><CardDescription>{thread.phone}{thread.sessionOpen ? "" : ` · ${"More than 24 hours since they wrote: WhatsApp only allows templates now."}`}</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <ul className="max-h-96 space-y-2 overflow-y-auto text-sm">
            {thread.items.map((m, i) => (
              <li key={i} className={`max-w-[85%] rounded-xl border border-line px-3 py-2 ${m.direction === "out" ? "ml-auto bg-accent/10" : "bg-surface-2"}`}>
                <p className="whitespace-pre-wrap text-ink-2" dir="auto">{m.text ?? `[${m.kind}]`}</p>
                <p className="text-[11px] text-muted">{formatWhen(m.at)}{m.direction === "out" ? ` · ${m.kind === "typed" ? "typed by you" : "automatic"}${m.status ? ` · ${m.status}` : ""}` : ""}</p>
              </li>
            ))}
          </ul>

          {s ? (
            <div className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
              <p className="text-xs text-muted">{(INTENT[s.intent] ?? s.intent)} · a guess from keywords</p>
              {s.draft ? (
                <>
                  <p className="mt-1 whitespace-pre-wrap text-ink-2">{s.draft}</p>
                  <p className="mt-1 text-[11px] text-muted">{s.label} {s.sources.join(", ")}</p>
                  <Button variant="secondary" className="mt-2" onClick={() => setText(s.draft ?? "")}>Use this draft</Button>
                </>
              ) : <p className="mt-1 text-warning">{(s.reason ?? "A person should answer this.")}</p>}
            </div>
          ) : null}

          <div className="flex gap-2">
            <Input value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} placeholder="Write a reply" aria-label="Reply" dir="auto" />
            <Button disabled={busy || !text.trim()} onClick={() => run(async () => { await sendReply(id, text.trim()); setText(""); })}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}Send</Button>
          </div>
          <div aria-live="polite">{error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}</div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Inside notes and owner</CardTitle><CardDescription>The customer never sees these.</CardDescription></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <ul className="space-y-1 text-ink-2">{thread.notes.map((n) => <li key={n.id}><span className="text-xs text-muted">{formatWhen(n.at)} · {n.author ?? ""}</span> {n.body}</li>)}</ul>
          <div className="flex gap-2"><Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} placeholder="Add a note" aria-label="Note" /><Button variant="secondary" disabled={!note.trim()} onClick={() => run(async () => { await addNote(id, note.trim()); setNote(""); })}>Add</Button></div>
          <div className="flex flex-wrap items-end gap-2">
            <label className={field}>Owner of this chat (email)<Input value={owner} onChange={(e) => setOwner(e.target.value)} maxLength={320} className="w-64" /></label>
            <Button variant="secondary" onClick={() => run(() => assignConversation(id, { assignedTo: owner }))}>Assign</Button>
            <Button variant="ghost" onClick={() => run(() => assignConversation(id, { status: thread.status === "open" ? "closed" : "open" }))}>{thread.status === "open" ? "Close" : "Reopen"}</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function FaqCard() {
  const [faq, setFaq] = useState<Faq[]>([]);
  const [v, setV] = useState({ title: "", keywords: "", answer: "" });
  const [version, setVersion] = useState(0);
  useEffect(() => {
    listFaq().then(setFaq).catch(() => undefined);
  }, [version]);
  return (
    <Card>
      <CardHeader><CardTitle>Your ready answers</CardTitle><CardDescription>Drafts may use only these, your orders and your stock list. Add the questions customers ask most (delivery time, return window...).</CardDescription></CardHeader>
      <CardContent className="space-y-3 text-sm">
        <ul className="space-y-1 text-ink-2">{faq.map((f) => <li key={f.id}><strong className="text-ink">{f.title}</strong> ({f.keywords}): {f.answer}</li>)}</ul>
        <div className="grid gap-2 sm:grid-cols-[1fr_1fr_2fr_auto] sm:items-end">
          <label className={field}>Title<Input value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} maxLength={120} /></label>
          <label className={field}>Words that bring it up (commas)<Input value={v.keywords} onChange={(e) => setV({ ...v, keywords: e.target.value })} maxLength={300} /></label>
          <label className={field}>The answer<Input value={v.answer} onChange={(e) => setV({ ...v, answer: e.target.value })} maxLength={2000} /></label>
          <Button disabled={!v.title.trim() || !v.keywords.trim() || !v.answer.trim()} onClick={async () => { await addFaq(v).catch(() => undefined); setV({ title: "", keywords: "", answer: "" }); setVersion((x) => x + 1); }}>Add</Button>
        </div>
      </CardContent>
    </Card>
  );
}
