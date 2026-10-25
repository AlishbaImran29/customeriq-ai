"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus } from "lucide-react";
import { formatWhen } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { API_MODE, ApiError } from "@/lib/api/config";
import { addTicketNote, changeTicket, createTicket, getTicket, listTickets, type Ticket } from "@/lib/api/returns";
import { useLanguage } from "@/lib/i18n";

const field = "flex flex-col gap-1 text-sm font-medium text-ink-2";
const STATUS: Ticket["status"][] = ["open", "in_progress", "resolved", "closed"];
const LABEL: Record<Ticket["status"], string> = { open: "Open", in_progress: "In progress", resolved: "Resolved", closed: "Closed" };

/** Complaints and questions to follow up: an owner, a status, a priority and internal notes. */
export function TicketsBoard() {
  const { t } = useLanguage();
  if (API_MODE !== "live") return <p className="text-sm text-muted">{t("Tickets are saved in your database. Connect the backend to use them.")}</p>;
  return <TicketsContent />;
}

function TicketsContent() {
  const { t } = useLanguage();
  const [show, setShow] = useState<"all" | Ticket["status"]>("all");
  const [rows, setRows] = useState<Ticket[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listTickets(show === "all" ? undefined : show)
      .then((r) => !cancelled && (setRows(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [show, version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (failed) return <ErrorState title={t("Could not load the tickets")} description={t("Please check your connection and reload the page.")} />;
  return (
    <div className="space-y-5">
      <NewTicket onAdded={reload} />
      <FilterPills label={t("Filter by status")} value={show} onChange={setShow} options={[{ value: "all" as const, label: t("All") }, ...STATUS.map((s) => ({ value: s, label: t(LABEL[s]) }))]} />
      {!rows ? <Skeleton className="h-40 w-full" /> : rows.length === 0 ? <p className="text-sm text-muted">{t("No tickets here.")}</p> : (
        <ul className="space-y-3">{rows.map((tk) => <TicketCard key={tk.id} ticket={tk} onChanged={reload} />)}</ul>
      )}
    </div>
  );
}

function NewTicket({ onAdded }: { onAdded: () => void }) {
  const { t } = useLanguage();
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [priority, setPriority] = useState<Ticket["priority"]>("normal");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createTicket({ subject: subject.trim(), body: body.trim() || undefined, priority });
      setSubject("");
      setBody("");
      onAdded();
    } catch (err) {
      setError(err instanceof ApiError ? t(err.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle>{t("Open a ticket")}</CardTitle><CardDescription>{t("A complaint or question that needs a follow-up.")}</CardDescription></CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[2fr_2fr_1fr_auto] sm:items-end" noValidate>
          <label className={field}>{t("Subject")}<Input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={200} /></label>
          <label className={field}>{t("Details (optional)")}<Input value={body} onChange={(e) => setBody(e.target.value)} maxLength={4000} /></label>
          <label className={field}>{t("Priority")}<Select value={priority} onChange={(e) => setPriority(e.target.value as Ticket["priority"])} className="w-full"><option value="low">{t("Low")}</option><option value="normal">{t("Normal")}</option><option value="high">{t("High")}</option></Select></label>
          <Button type="submit" disabled={busy || subject.trim().length < 3}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}{t("Add")}</Button>
          {error ? <p role="alert" className="text-sm text-danger sm:col-span-4">{error}</p> : null}
        </form>
      </CardContent>
    </Card>
  );
}

function TicketCard({ ticket, onChanged }: { ticket: Ticket; onChanged: () => void }) {
  const { t } = useLanguage();
  const [detail, setDetail] = useState<Ticket | null>(null);
  const [owner, setOwner] = useState(ticket.assignedTo ?? "");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const shown = detail ?? ticket;

  async function run(work: () => Promise<Ticket | void>) {
    setError(null);
    try {
      const r = await work();
      if (r) setDetail(r);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    }
  }

  return (
    <li>
      <Card>
        <CardContent className="space-y-2 pt-5 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-ink">{ticket.subject}</span>
            <span className="rounded-full bg-surface-3 px-2 py-0.5 text-[11px] font-medium text-ink-2">{t(LABEL[shown.status])}</span>
            {ticket.priority === "high" ? <span className="rounded-full bg-danger/15 px-2 py-0.5 text-[11px] font-medium text-danger">{t("High")}</span> : null}
            <span className="ml-auto text-xs text-muted">{ticket.customerName ?? ""} · {formatWhen(ticket.createdAt)}</span>
          </div>
          {ticket.body ? <p className="text-ink-2">{ticket.body}</p> : null}
          <div className="flex flex-wrap items-end gap-2">
            <Select value={shown.status} onChange={(e) => run(() => changeTicket(ticket.id, { status: e.target.value as Ticket["status"] }))} aria-label={t("Status")}>{STATUS.map((s) => <option key={s} value={s}>{t(LABEL[s])}</option>)}</Select>
            <Input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder={t("Owner (email)")} className="w-56" maxLength={320} />
            <Button variant="secondary" onClick={() => run(() => changeTicket(ticket.id, { assignedTo: owner }))}>{t("Assign")}</Button>
            {!detail ? <Button variant="ghost" onClick={() => run(() => getTicket(ticket.id))}>{t("Show notes")}</Button> : null}
          </div>
          {detail ? (
            <>
              <ul className="space-y-1 text-xs text-ink-2">{detail.notes.map((n) => <li key={n.id}>{formatWhen(n.at)} · {n.author ?? ""}: {n.text}</li>)}</ul>
              <div className="flex gap-2">
                <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("Add a note")} maxLength={2000} />
                <Button variant="secondary" disabled={!note.trim()} onClick={() => run(async () => { const r = await addTicketNote(ticket.id, note.trim()); setNote(""); return r; })}>{t("Add")}</Button>
              </div>
            </>
          ) : null}
          <div aria-live="polite">{error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}</div>
        </CardContent>
      </Card>
    </li>
  );
}
