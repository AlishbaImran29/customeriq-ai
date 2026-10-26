"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { API_MODE, ApiError } from "@/lib/api/config";
import { anonymiseCustomer, deleteCustomer, getProfile, getTimeline, saveProfile, type CustomerProfile, type TimelineEvent } from "@/lib/api/customer-records";
import { formatDate } from "@/lib/utils";

const field = "flex flex-col gap-1 text-sm font-medium text-ink-2";
const KIND: Record<TimelineEvent["kind"], string> = { order: "Order", status: "Status", message: "Message sent", reply: "Customer wrote", consent: "Consent" };

/** Notes, tags and source for one customer, their full timeline, and the two ways to erase them (anonymise keeps the orders as anonymous figures). */
export function CustomerTools({ customerId }: { customerId: string }) {
  if (API_MODE !== "live") return null;
  return (
    <div className="space-y-4">
      <Record customerId={customerId} />
      <Timeline customerId={customerId} />
      <Erase customerId={customerId} />
    </div>
  );
}

function Record({ customerId }: { customerId: string }) {
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [notes, setNotes] = useState("");
  const [tags, setTags] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getProfile(customerId)
      .then((p) => {
        if (cancelled) return;
        setProfile(p);
        setNotes(p.notes ?? "");
        setTags(p.tags.join(", "));
        setSource(p.acquisitionSource ?? "");
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [customerId]);

  async function save() {
    setBusy(true);
    setNote(null);
    try {
      const p = await saveProfile(customerId, { notes, tags: tags.split(",").map((x) => x.trim()).filter(Boolean), acquisitionSource: source });
      setProfile(p);
      setTags(p.tags.join(", "));
      setNote("Saved.");
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!profile) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Notes and tags</CardTitle>
        <CardDescription>Only you see these. Do not store card numbers or passwords here.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <label className={field}>Notes<textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} maxLength={2000} className="w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink" /></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className={field}>Tags (separated by commas)<Input value={tags} onChange={(e) => setTags(e.target.value)} maxLength={400} /></label>
          <label className={field}>Where did this customer come from?<Input value={source} onChange={(e) => setSource(e.target.value)} maxLength={60} placeholder="Instagram, referral..." /></label>
        </div>
        <div className="flex items-center gap-3" aria-live="polite">
          <Button onClick={save} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}Save</Button>
          {note ? <span className="text-sm text-ink-2">{note}</span> : null}
        </div>
      </CardContent>
    </Card>
  );
}

function Timeline({ customerId }: { customerId: string }) {
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    getTimeline(customerId)
      .then((r) => !cancelled && setEvents(r))
      .catch(() => !cancelled && setEvents([]));
    return () => {
      cancelled = true;
    };
  }, [customerId]);
  if (!events) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Timeline</CardTitle>
        <CardDescription>Orders, status changes, messages, replies and consent, newest first.</CardDescription>
      </CardHeader>
      <CardContent>
        {events.length === 0 ? <p className="text-sm text-muted">Nothing yet.</p> : (
          <ul className="space-y-1.5 text-sm text-ink-2">
            {events.slice(0, 60).map((e, i) => <li key={i}><span className="text-xs text-muted">{formatDate(e.at)} · {KIND[e.kind]}</span> {e.text}</li>)}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function Erase({ customerId }: { customerId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function run(kind: "anonymise" | "delete") {
    const sure = kind === "anonymise"
      ? "Erase this customer's name, phone, email, notes and all messages? Their orders stay as anonymous figures. This cannot be undone."
      : "Delete this customer and ALL their orders? This cannot be undone.";
    if (!window.confirm(sure)) return;
    setBusy(true);
    setNote(null);
    try {
      if (kind === "anonymise") await anonymiseCustomer(customerId);
      else await deleteCustomer(customerId);
      router.push("/segmentation");
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><ShieldAlert className="h-4 w-4 text-warning" aria-hidden="true" />Erase this customer</CardTitle>
        <CardDescription>If the customer asks you to delete their data. Anonymising keeps your sales figures true; deleting removes the orders too.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-3" aria-live="polite">
        <Button variant="secondary" disabled={busy} onClick={() => run("anonymise")}>Erase personal data</Button>
        <Button variant="ghost" disabled={busy} onClick={() => run("delete")}>Delete customer and orders</Button>
        {note ? <p role="alert" className="text-sm text-danger">{note}</p> : null}
      </CardContent>
    </Card>
  );
}
