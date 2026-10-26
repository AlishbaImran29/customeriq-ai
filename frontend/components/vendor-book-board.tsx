"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BadgeCheck, CircleDollarSign, ExternalLink, Loader2, MessageCircle, Pencil, Plus, Save, Sparkles, Trash2, Zap } from "lucide-react";
import { LaunchStepFrame } from "@/components/launch-step-frame";
import { Money } from "@/components/money";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input, Select } from "@/components/ui/input";
import {
  addQuote, addVendor, chooseVendor, editVendor, listQuotes, listVendors, removeQuote, removeVendor, requestQuote,
  type Language, type Quote, type QuoteMessage, type Vendor,
} from "@/lib/api/launch-steps";
import { ApiError } from "@/lib/api/config";
import type { Project } from "@/lib/api/launch";
import { waMeLink } from "@/lib/launch-links";
import { formatNumber, formatPercent } from "@/lib/utils";
import { fmt } from "@/lib/format";

const field = "space-y-1 text-xs font-medium text-muted";
const areaClass =
  "min-h-28 w-full rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-faint outline-none transition focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

/** Step 2: the vendor book, the quotes for the chosen project side by side, and the AI-written message asking for a quote. */
export function VendorBookBoard() {
  return <LaunchStepFrame step={2}>{(project) => <VendorStep project={project} />}</LaunchStepFrame>;
}

function VendorStep({ project }: { project: Project }) {
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reloadVendors = useCallback(() => {
    listVendors().then(setVendors).catch(() => setError("Something went wrong. Please try again."));
  }, []);

  useEffect(() => {
    reloadVendors();
  }, [reloadVendors]);

  useEffect(() => {
    let cancelled = false;
    listQuotes(project.id)
      .then((q) => !cancelled && setQuotes(q))
      .catch(() => !cancelled && setError("Something went wrong. Please try again."));
    return () => {
      cancelled = true;
    };
  }, [project.id]);

  return (
    <div className="space-y-5">
      <div aria-live="polite">{error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}</div>
      <QuoteTable project={project} vendors={vendors} quotes={quotes} setQuotes={setQuotes} onError={setError} onChanged={reloadVendors} />
      <VendorBook project={project} vendors={vendors} onChanged={reloadVendors} />
    </div>
  );
}

// --------------------------------------------------------------------------------------------- quotes

type SortKey = "price" | "delivery" | "moq";

function QuoteTable({
  project, vendors, quotes, setQuotes, onError, onChanged,
}: {
  project: Project; vendors: Vendor[]; quotes: Quote[]; setQuotes: (q: Quote[]) => void; onError: (m: string | null) => void; onChanged: () => void;
}) {
  const [sort, setSort] = useState<SortKey>("price");
  const sorted = useMemo(() => {
    const key = (q: Quote) => (sort === "price" ? q.unitPrice : sort === "delivery" ? q.deliveryDays ?? Infinity : q.moq ?? Infinity);
    return [...quotes].sort((a, b) => key(a) - key(b));
  }, [quotes, sort]);

  async function choose(q: Quote) {
    try {
      setQuotes(await chooseVendor(project.id, q.chosen ? null : q.vendorId));
      onChanged();
    } catch {
      onError("Something went wrong. Please try again.");
    }
  }

  async function remove(q: Quote) {
    try {
      setQuotes(await removeQuote(q.id));
    } catch {
      onError("Something went wrong. Please try again.");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{fmt("Quotes for {product}", { product: project.productName })}</CardTitle>
        <CardDescription>{"Put the vendors' offers side by side. The cheapest and the fastest are marked."}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {quotes.length > 1 ? (
          <FilterPills
            label="Sort quotes by"
            value={sort}
            onChange={setSort}
            options={[{ value: "price" as SortKey, label: "Price" }, { value: "delivery" as SortKey, label: "Delivery time" }, { value: "moq" as SortKey, label: "Minimum order" }]}
          />
        ) : null}
        {quotes.length === 0 ? <p className="text-sm text-muted">No quotes yet. Add one below after the vendor replies.</p> : (
          <>
            <ul className="space-y-3 md:hidden">
              {sorted.map((q) => (
                <li key={q.id} className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
                  <p className="font-medium text-ink">{q.vendorName} <Marks q={q} /></p>
                  <p className="text-ink-2"><Money value={q.unitPrice} /> · Minimum order: {q.moq ?? "-"} · {q.deliveryDays === null ? "-" : fmt("{days} days", { days: q.deliveryDays })}</p>
                  <QuoteExtras q={q} />
                  <QuoteActions q={q} onChoose={choose} onRemove={remove} />
                </li>
              ))}
            </ul>
            <div className="hidden md:block">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Quotes</caption>
                <thead className="text-xs text-muted">
                  <tr className="border-b border-line">
                    <th scope="col" className="py-2 pr-3 font-medium">Vendor</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">Price per piece</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">Minimum order</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">Delivery time</th>
                    <th scope="col" className="py-2 pr-3 font-medium">Notes</th>
                    <th scope="col" className="py-2 font-medium"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((q) => (
                    <tr key={q.id} className="border-b border-line/60 align-top">
                      <td className="py-2.5 pr-3 font-medium text-ink">{q.vendorName} <Marks q={q} /></td>
                      <td className="py-2.5 pr-3 text-right tabular-nums"><Money value={q.unitPrice} /></td>
                      <td className="py-2.5 pr-3 text-right tabular-nums">{q.moq === null ? "-" : formatNumber(q.moq)}</td>
                      <td className="py-2.5 pr-3 text-right tabular-nums">{q.deliveryDays === null ? "-" : fmt("{days} days", { days: q.deliveryDays })}</td>
                      <td className="py-2.5 pr-3 text-ink-2"><QuoteExtras q={q} /></td>
                      <td className="py-2.5"><QuoteActions q={q} onChoose={choose} onRemove={remove} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        <AddQuote project={project} vendors={vendors} setQuotes={setQuotes} onError={onError} />
      </CardContent>
    </Card>
  );
}

/** Cheapest / fastest / chosen: an icon AND a word, never colour alone. */
function Marks({ q }: { q: Quote }) {
  const mark = "ml-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium";
  return (
    <>
      {q.cheapest ? <span className={`${mark} bg-success/10 text-success`}><CircleDollarSign className="h-3 w-3" aria-hidden="true" />Cheapest</span> : null}
      {q.fastest ? <span className={`${mark} bg-info/10 text-info`}><Zap className="h-3 w-3" aria-hidden="true" />Fastest</span> : null}
      {q.chosen ? <span className={`${mark} bg-accent/10 text-accent`}><BadgeCheck className="h-3 w-3" aria-hidden="true" />Chosen</span> : null}
    </>
  );
}

function QuoteExtras({ q }: { q: Quote }) {
  return (
    <span className="block text-xs text-ink-2">
      {q.sampleReceived ? "Sample received" : "No sample yet"}
      {q.qualityNotes ? ` · ${q.qualityNotes}` : ""}
    </span>
  );
}

function QuoteActions({ q, onChoose, onRemove }: { q: Quote; onChoose: (q: Quote) => void; onRemove: (q: Quote) => void }) {
  return (
    <span className="mt-2 flex flex-wrap gap-2 md:mt-0">
      <Button variant="secondary" onClick={() => onChoose(q)}>
        <BadgeCheck className="h-4 w-4" aria-hidden="true" />
        {q.chosen ? "Unchoose" : "Choose this vendor"}
      </Button>
      <Button variant="ghost" onClick={() => onRemove(q)} aria-label={fmt("Delete the quote from {vendor}", { vendor: q.vendorName })}>
        <Trash2 className="h-4 w-4" aria-hidden="true" />
      </Button>
    </span>
  );
}

function AddQuote({ project, vendors, setQuotes, onError }: { project: Project; vendors: Vendor[]; setQuotes: (q: Quote[]) => void; onError: (m: string | null) => void }) {
  const [vendorId, setVendorId] = useState("");
  const [price, setPrice] = useState("");
  const [moq, setMoq] = useState("");
  const [days, setDays] = useState("");
  const [notes, setNotes] = useState("");
  const [sample, setSample] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    onError(null);
    const unit = Number(price.replace(/,/g, ""));
    if (!vendorId) return onError("Choose a vendor.");
    if (!Number.isFinite(unit) || unit < 0 || price.trim() === "") return onError("Enter the price per piece.");
    setBusy(true);
    try {
      setQuotes(await addQuote(project.id, {
        vendorId: Number(vendorId), unitPrice: unit, moq: moq ? Number(moq) : undefined, deliveryDays: days ? Number(days) : undefined,
        qualityNotes: notes.trim() || undefined, sampleReceived: sample,
      }));
      setPrice(""); setMoq(""); setDays(""); setNotes(""); setSample(false);
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (vendors.length === 0) return <p className="text-sm text-muted">Add a vendor in the vendor book below first.</p>;
  return (
    <form onSubmit={submit} className="grid gap-3 border-t border-line pt-4 sm:grid-cols-2 lg:grid-cols-3" noValidate>
      <p className="text-sm font-medium text-ink sm:col-span-2 lg:col-span-3">Add a quote</p>
      <label className={field}>Vendor
        <Select value={vendorId} onChange={(e) => setVendorId(e.target.value)} className="w-full">
          <option value="">Choose a vendor</option>
          {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
        </Select>
      </label>
      <label className={field}>Price per piece (PKR)<Input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} /></label>
      <label className={field}>Minimum order<Input inputMode="numeric" value={moq} onChange={(e) => setMoq(e.target.value.replace(/\D/g, ""))} /></label>
      <label className={field}>Delivery time (days)<Input inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value.replace(/\D/g, ""))} /></label>
      <label className={`${field} lg:col-span-2`}>Quality notes (optional)<Input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} /></label>
      <label className="flex items-center gap-2 text-sm text-ink-2">
        <input type="checkbox" checked={sample} onChange={(e) => setSample(e.target.checked)} className="h-4 w-4 accent-[var(--color-accent)]" />
        Sample received
      </label>
      <div><Button type="submit" disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}Add quote</Button></div>
    </form>
  );
}

// ----------------------------------------------------------------------------------------- vendor book

function VendorBook({ project, vendors, onChanged }: { project: Project; vendors: Vendor[]; onChanged: () => void }) {
  const [editing, setEditing] = useState<Vendor | "new" | null>(null);
  const [asking, setAsking] = useState<Vendor | null>(null);
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>Vendor book</CardTitle>
          <CardDescription>Your suppliers, with their WhatsApp numbers.</CardDescription>
        </div>
        <Button onClick={() => setEditing("new")}><Plus className="h-4 w-4" aria-hidden="true" />Add vendor</Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {editing ? <VendorForm vendor={editing === "new" ? null : editing} onDone={() => { setEditing(null); onChanged(); }} onCancel={() => setEditing(null)} /> : null}
        {vendors.length === 0 && !editing ? <p className="text-sm text-muted">No vendors yet.</p> : null}
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {vendors.map((v) => (
            <li key={v.id} className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
              <p className="font-medium text-ink">{v.name}</p>
              <p className="text-xs text-muted">{[v.city, v.categories].filter(Boolean).join(" · ") || "-"}</p>
              <p className="mt-1 text-ink-2">{v.whatsappPhone ?? "No WhatsApp number"}</p>
              {v.notes ? <p className="mt-1 text-xs text-ink-2">{v.notes}</p> : null}
              <Quality v={v} />
              <div className="mt-2 flex flex-wrap gap-2">
                <Button variant="secondary" onClick={() => setAsking(asking?.id === v.id ? null : v)}><MessageCircle className="h-4 w-4" aria-hidden="true" />Request quote</Button>
                <Button variant="ghost" onClick={() => setEditing(v)} aria-label={`${"Edit"} ${v.name}`}><Pencil className="h-4 w-4" aria-hidden="true" /></Button>
                <DeleteVendor vendor={v} onDone={onChanged} />
              </div>
              {asking?.id === v.id ? <RequestQuote project={project} vendor={v} /> : null}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

/** A vendor's return rate: only with enough orders of known outcome, otherwise "Not enough data yet". */
function Quality({ v }: { v: Vendor }) {
  const q = v.quality;
  return (
    <p className="mt-1 text-xs text-muted">
      {q.returnRate !== null
        ? fmt("Return rate of orders for this vendor's products: {rate} ({orders} orders)", { rate: formatPercent(q.returnRate * 100, 0), orders: q.closedOrders })
        : `${"Return rate"}: ${"Not enough data yet"} ${fmt("({orders} orders so far, {needed} more needed)", { orders: q.closedOrders, needed: q.needed })}`}
    </p>
  );
}

function DeleteVendor({ vendor, onDone }: { vendor: Vendor; onDone: () => void }) {
  const [confirming, setConfirming] = useState(false);
  if (!confirming) return <Button variant="ghost" onClick={() => setConfirming(true)} aria-label={fmt("Delete {product}", { product: vendor.name })}><Trash2 className="h-4 w-4" aria-hidden="true" /></Button>;
  return (
    <span className="flex gap-2">
      <Button onClick={async () => { await removeVendor(vendor.id).catch(() => undefined); onDone(); }} className="bg-danger text-white hover:bg-danger/90">Yes, delete</Button>
      <Button variant="secondary" onClick={() => setConfirming(false)}>Cancel</Button>
    </span>
  );
}

function VendorForm({ vendor, onDone, onCancel }: { vendor: Vendor | null; onDone: () => void; onCancel: () => void }) {
  const [name, setName] = useState(vendor?.name ?? "");
  const [phone, setPhone] = useState(vendor?.whatsappPhone ?? "");
  const [city, setCity] = useState(vendor?.city ?? "");
  const [categories, setCategories] = useState(vendor?.categories ?? "");
  const [notes, setNotes] = useState(vendor?.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (name.trim().length < 2) return setError("Give the vendor a name of at least 2 characters.");
    setBusy(true);
    try {
      const body = { name: name.trim(), whatsappPhone: phone.trim(), city: city.trim(), categories: categories.trim(), notes: notes.trim() };
      if (vendor) await editVendor(vendor.id, body);
      else await addVendor(body);
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 rounded-xl border border-line bg-surface-2 p-3 sm:grid-cols-2" noValidate>
      <label className={field}>Vendor name<Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} /></label>
      <label className={field}>WhatsApp number<Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="0300 1234567" inputMode="tel" /></label>
      <label className={field}>City<Input value={city} onChange={(e) => setCity(e.target.value)} maxLength={100} /></label>
      <label className={field}>What they sell<Input value={categories} onChange={(e) => setCategories(e.target.value)} maxLength={300} /></label>
      <label className={`${field} sm:col-span-2`}>Notes<Input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={4000} /></label>
      <div className="flex flex-wrap items-center gap-2 sm:col-span-2" aria-live="polite">
        <Button type="submit" disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}Save vendor</Button>
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
      </div>
    </form>
  );
}

/** The AI writes a polite message; the seller edits it and sends it from WhatsApp themselves (the app never sends). */
function RequestQuote({ project, vendor }: { project: Project; vendor: Vendor }) {
  const [quantity, setQuantity] = useState("100");
  const [language, setLanguage] = useState<Language>("ur");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<QuoteMessage | null>(null);
  const [text, setText] = useState("");
  const [copied, setCopied] = useState(false);

  async function write(force: boolean) {
    setError(null);
    const count = Number(quantity);
    if (!Number.isInteger(count) || count < 1) return setError("Enter how many pieces you want to ask about.");
    setBusy(true);
    try {
      const result = await requestQuote(vendor.id, { projectId: project.id, quantity: count, language, force });
      setDraft(result);
      setText(result.message);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const link = waMeLink(vendor.whatsappPhone, text);
  return (
    <div className="mt-3 space-y-3 border-t border-line pt-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className={field}>How many pieces?<Input inputMode="numeric" value={quantity} onChange={(e) => setQuantity(e.target.value.replace(/\D/g, ""))} /></label>
        <div className={field}>
          <span>Message language</span>
          <FilterPills label="Message language" value={language} onChange={setLanguage}
            options={[{ value: "ur" as Language, label: "اردو" }, { value: "roman_ur" as Language, label: "Roman Urdu" }, { value: "en" as Language, label: "English" }]} />
        </div>
      </div>
      <Button onClick={() => write(false)} disabled={busy}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}
        Write the message with AI
      </Button>
      <div aria-live="polite">{error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}</div>
      {draft ? (
        <div className="space-y-2">
          <p className="text-xs text-muted">
            <span className="rounded-full bg-accent/10 px-2 py-0.5 font-medium text-accent">AI suggestion</span>{" "}
            Read it and change anything you like. Nothing is sent until you press send in WhatsApp.
          </p>
          <textarea className={areaClass} value={text} onChange={(e) => setText(e.target.value)} maxLength={900} aria-label="Message to the vendor" dir="auto" />
          <div className="flex flex-wrap items-center gap-2">
            {link ? (
              <a href={link} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3.5 py-2 text-sm font-medium text-ink-2 hover:bg-surface-3 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
                <ExternalLink className="h-4 w-4" aria-hidden="true" />Open in WhatsApp
              </a>
            ) : (
              <span className="text-xs text-muted">{vendor.whatsappPhone ? "Write a message first." : "This vendor has no WhatsApp number, so there is no link. Add the number to the vendor first."}</span>
            )}
            <Button variant="secondary" onClick={async () => { await navigator.clipboard?.writeText(text).catch(() => undefined); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
              {copied ? "Copied" : "Copy"}
            </Button>
            <Button variant="ghost" onClick={() => write(true)} disabled={busy}>Write another</Button>
          </div>
          <p className="text-xs text-muted">{draft.cached ? "Saved answer: no new AI call was made." : draft.model ? fmt("Written by {model}.", { model: draft.model }) : ""}</p>
        </div>
      ) : null}
    </div>
  );
}
