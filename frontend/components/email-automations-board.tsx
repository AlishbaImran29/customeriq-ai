"use client";

import { useCallback, useEffect, useState } from "react";
import { MessengerGate, formatWhen } from "@/components/messenger-bits";
import { Money } from "@/components/money";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import {
  createAnnouncement, getAnnouncementPreview, getOverview, getPreviews, loadSampleData, refreshLifecycle, saveSettings, sendAnnouncement, sendCod, sendTestEmails, sendWinback,
  type AnnouncementPreview, type AnnounceInput, type BulkResult, type CodEmailStatus, type EmailOverview, type Preview,
} from "@/lib/api/email-auto";

const STATUS_LABEL: Record<CodEmailStatus, string> = { pending: "Pending", confirmed: "Confirmed", cancelled: "Cancelled" };
const STATUS_TONE: Record<CodEmailStatus, string> = { pending: "bg-warning/15 text-warning", confirmed: "bg-success/15 text-success", cancelled: "bg-danger/15 text-danger" };
const problem = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Please try again.");

function bulkText(r: BulkResult): string {
  const skipped = Object.entries(r.skipped).map(([why, n]) => `${n} skipped (${why})`);
  const parts = [`${r.sent} ${r.testMode ? "prepared in test mode (not really sent)" : "sent"}`, ...(r.failed ? [`${r.failed} failed`] : []), ...skipped, ...(r.remaining ? [`${r.remaining} still waiting: press the button again`] : [])];
  return [parts.join(", ") + ".", r.message].filter(Boolean).join(" ");
}

export function EmailAutomationsBoard() {
  return (
    <MessengerGate>
      <Content />
    </MessengerGate>
  );
}

function Content() {
  const [data, setData] = useState<EmailOverview | null>(null);
  const [failed, setFailed] = useState(false);
  const [note, setNote] = useState<{ text: string; bad: boolean } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const reload = useCallback(() => {
    getOverview().then((d) => (setData(d), setFailed(false))).catch(() => setFailed(true));
  }, []);
  useEffect(reload, [reload]);

  /** Runs one action: shows a busy state, then its result (or the problem) as a message. */
  async function run(name: string, work: () => Promise<string>) {
    setBusy(name);
    setNote(null);
    try {
      setNote({ text: await work(), bad: false });
    } catch (e) {
      setNote({ text: problem(e), bad: true });
    } finally {
      setBusy(null);
      reload();
    }
  }

  if (failed) return <ErrorState title="Could not load Email Automations" description="Please check your connection and reload the page. If this is new, the database migration 0035 must be run first." />;
  if (!data) return <Skeleton className="h-64 w-full" />;

  return (
    <div className="space-y-6">
      <Status data={data} />
      {note && (
        <p role="status" className={`rounded-md border px-3 py-2 text-sm ${note.bad ? "border-danger/40 bg-danger/10 text-danger" : "border-success/40 bg-success/10 text-success"}`}>
          {note.text}
        </p>
      )}
      <CodSection data={data} busy={busy} run={run} />
      <WinbackSection data={data} busy={busy} run={run} />
      <ProductSection data={data} busy={busy} run={run} />
      <PreviewSection />
      <LookSection data={data} busy={busy} run={run} />
      <TestSection busy={busy} run={run} />
    </div>
  );
}

type Run = (name: string, work: () => Promise<string>) => Promise<void>;
type SectionProps = { data: EmailOverview; busy: string | null; run: Run };

function Status({ data }: { data: EmailOverview }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Emails sent today</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{data.sentToday} <span className="text-base font-normal text-muted">of {data.dailyLimit}</span></p>
          <p className="text-xs text-muted">Marketing stops at {data.marketingCap}; the rest is kept for COD emails.</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">At risk / lost customers</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums">{data.lifecycle.at_risk ?? 0} <span className="text-base font-normal text-muted">/ {data.lifecycle.lost ?? 0}</span></p>
          <p className="text-xs text-muted">No order for 60+ / 180+ days.</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Mode</p>
          <p className="mt-2 text-2xl font-semibold">{data.testMode ? "Test mode" : "Live"}</p>
          <p className="text-xs text-muted">{data.testMode ? "BREVO_API_KEY or SENDER_EMAIL is missing: nothing is really sent." : `Sending from ${data.senderEmail}.`}</p>
        </Card>
      </div>
      {!data.linksReady && (
        <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
          MESSAGING_SECRET and PUBLIC_API_URL are not set on the server. Without them the confirm, cancel and unsubscribe links cannot be made, so COD and marketing emails will be refused.
        </p>
      )}
    </div>
  );
}

function CodSection({ data, busy, run }: SectionProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>COD confirmation emails</CardTitle>
        <CardDescription>A new cash-on-delivery order with an email address gets a confirmation email. The status changes only when the customer presses the button on the page. No answer in 24 hours sends one reminder.</CardDescription>
      </CardHeader>
      <CardContent>
        {data.cod.length === 0 ? (
          <p className="text-sm text-muted">No COD emails yet. They are sent automatically for new COD orders (Shopify or Add Order). In test mode, load the sample data below and press Send on the sample order.</p>
        ) : (
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <caption className="sr-only">COD orders and their email status</caption>
              <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">Order</th>
                  <th scope="col" className="px-3 py-2 font-medium">Customer</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Total</th>
                  <th scope="col" className="px-3 py-2 font-medium">Status</th>
                  <th scope="col" className="px-3 py-2 font-medium">Email sent</th>
                  <th scope="col" className="px-3 py-2"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {data.cod.map((r) => (
                  <tr key={r.orderId} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2 font-medium">#{r.orderNumber}</td>
                    <td className="px-3 py-2">{r.customerName}<span className="block text-xs text-muted">{r.email ?? "no email"}</span></td>
                    <td className="px-3 py-2 text-right tabular-nums"><Money value={r.amount} /></td>
                    <td className="px-3 py-2"><span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_TONE[r.status]}`}>{STATUS_LABEL[r.status]}</span></td>
                    <td className="px-3 py-2 text-xs text-muted">{formatWhen(r.sentAt)}{r.reminderSentAt ? <span className="block">Reminder {formatWhen(r.reminderSentAt)}</span> : null}</td>
                    <td className="px-3 py-2 text-right">
                      {r.status === "pending" && !r.reminderSentAt && (
                        <Button variant="secondary" disabled={busy !== null} onClick={() => run(`cod${r.orderId}`, async () => { const x = await sendCod(r.orderId, true); return x.testMode ? "Reminder prepared in test mode (not really sent)." : "Reminder sent."; })}>
                          Send reminder
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function WinbackSection({ data, busy, run }: SectionProps) {
  const [code, setCode] = useState("");
  const [value, setValue] = useState("");
  return (
    <Card>
      <CardHeader>
        <CardTitle>Win-back emails</CardTitle>
        <CardDescription>
          Customers with no order for 60+ days are at risk, 180+ days lost. Only customers who agreed to email get it, nobody twice within 30 days, and every email has an unsubscribe link. Up to 100 emails per press.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-xs font-medium text-muted">Discount code (optional)
            <Input value={code} maxLength={30} placeholder="WELCOME10" onChange={(e) => setCode(e.target.value)} />
          </label>
          <label className="space-y-1 text-xs font-medium text-muted">What it gives (shown as &quot;to get ... off&quot;)
            <Input value={value} maxLength={20} placeholder="10% or Rs. 500" onChange={(e) => setValue(e.target.value)} />
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy !== null} onClick={() => run("winback", async () => bulkText(await sendWinback(code, value)))}>
            {busy === "winback" ? "Sending..." : "Send win-back emails"}
          </Button>
          <Button variant="secondary" disabled={busy !== null} onClick={() => run("lifecycle", async () => { const c = await refreshLifecycle(); return `Updated: ${c.active ?? 0} active, ${c.at_risk ?? 0} at risk, ${c.lost ?? 0} lost.`; })}>
            Update at-risk / lost list
          </Button>
        </div>
        {data.testMode && <p className="text-xs text-muted">Test mode: emails are written to the log, not sent.</p>}
      </CardContent>
    </Card>
  );
}

const EMPTY: AnnounceInput = { name: "" };

function ProductSection({ data, busy, run }: SectionProps) {
  const [form, setForm] = useState<AnnounceInput>(EMPTY);
  const [price, setPrice] = useState("");
  const [preview, setPreview] = useState<AnnouncementPreview | null>(null);
  const set = (key: keyof AnnounceInput) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [key]: e.target.value });

  async function show(id: number) {
    setPreview(await getAnnouncementPreview(id));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New product email</CardTitle>
        <CardDescription>
          A product added in Shopify creates a draft automatically. You can also announce one by hand. You preview it, then press Send: customers who bought from the same category get it first, then everyone else who agreed to email.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-xs font-medium text-muted">Product name
            <Input value={form.name} maxLength={120} onChange={set("name")} />
          </label>
          <label className="space-y-1 text-xs font-medium text-muted">Category (for the same-category first rule)
            <Input value={form.category ?? ""} maxLength={100} placeholder="Shoes" onChange={set("category")} />
          </label>
          <label className="space-y-1 text-xs font-medium text-muted">Price in Rs.
            <Input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
          </label>
          <label className="space-y-1 text-xs font-medium text-muted">Image web address
            <Input value={form.imageUrl ?? ""} placeholder="https://..." onChange={set("imageUrl")} />
          </label>
          <label className="space-y-1 text-xs font-medium text-muted sm:col-span-2">Product page web address (where Shop Now goes)
            <Input value={form.productUrl ?? ""} placeholder="https://..." onChange={set("productUrl")} />
          </label>
          <label className="space-y-1 text-xs font-medium text-muted sm:col-span-2">Description (two lines are shown)
            <Input value={form.description ?? ""} maxLength={1500} onChange={set("description")} />
          </label>
        </div>
        <Button
          disabled={busy !== null || !form.name.trim()}
          onClick={() => run("announce", async () => {
            const made = await createAnnouncement({ ...form, price: price.trim() ? Number(price) : undefined });
            await show(made.id);
            setForm(EMPTY);
            setPrice("");
            return "Draft created. Check the preview below, then press Send.";
          })}
        >
          Announce new product
        </Button>

        {data.announcements.length > 0 && (
          <ul className="divide-y divide-line/60 rounded-md border border-line">
            {data.announcements.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                <span><strong>{a.productName}</strong> <span className="text-muted">{a.category ?? ""}</span></span>
                <span className="flex items-center gap-2">
                  <span className="text-xs text-muted">{a.status === "sent" ? `Sent to ${a.sentCount}` : a.sentCount ? `Draft, ${a.sentCount} sent so far` : "Draft"}</span>
                  <Button variant="secondary" disabled={busy !== null} onClick={() => run("preview", async () => { await show(a.id); return "Preview opened below."; })}>Preview</Button>
                </span>
              </li>
            ))}
          </ul>
        )}

        {preview && (
          <div className="space-y-3 rounded-md border border-line p-3">
            <p className="text-sm"><strong>Subject:</strong> {preview.subject}</p>
            <p className="text-xs text-muted">
              Will go to {preview.audience.sameCategory} customers who bought from the same category first, then {preview.audience.others} others.
              {preview.audience.leftOut > 0 ? ` ${preview.audience.leftOut} are left out (no consent, or unsubscribed).` : ""}
            </p>
            <iframe title="Announcement preview" sandbox="" srcDoc={preview.html} className="h-[520px] w-full rounded-md border border-line bg-white" />
            {preview.status === "sent" ? (
              <p className="text-sm text-muted">This announcement was already sent to everyone.</p>
            ) : (
              <Button disabled={busy !== null} onClick={() => run("send-announcement", async () => bulkText(await sendAnnouncement(preview.id)))}>
                {busy === "send-announcement" ? "Sending..." : "Send"}
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PreviewSection() {
  const [items, setItems] = useState<Preview[] | null>(null);
  const [key, setKey] = useState("cod_confirmation");
  useEffect(() => {
    getPreviews().then(setItems).catch(() => setItems([]));
  }, []);
  const current = items?.find((p) => p.key === key);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Template previews</CardTitle>
        <CardDescription>Each email filled with sample data and your store look. The wording lives in backend/app/email_templates, one file per email.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!items ? <Skeleton className="h-40 w-full" /> : (
          <>
            <FilterPills label="Template" value={key} onChange={setKey} options={items.map((p) => ({ value: p.key, label: p.label }))} />
            {current && (
              <>
                <p className="text-sm"><strong>Subject:</strong> {current.subject}</p>
                <iframe title={`${current.label} preview`} sandbox="" srcDoc={current.html} className="h-[560px] w-full rounded-md border border-line bg-white" />
              </>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function LookSection({ data, busy, run }: SectionProps) {
  const s = data.settings;
  const [form, setForm] = useState({ storeName: s.storeName, logoUrl: s.logoUrl, brandColor: s.brandColor, supportEmail: s.supportEmail, storeUrl: s.storeUrl });
  const field = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [key]: e.target.value });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Email look</CardTitle>
        <CardDescription>Your logo, brand colour and contact shown in every email. Empty fields use safe defaults (store name {s.effective.storeName}, colour {s.effective.brandColor}).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-xs font-medium text-muted">Store name<Input value={form.storeName} maxLength={80} onChange={field("storeName")} /></label>
          <label className="space-y-1 text-xs font-medium text-muted">Brand colour (like #2563eb)<Input value={form.brandColor} maxLength={7} placeholder="#2563eb" onChange={field("brandColor")} /></label>
          <label className="space-y-1 text-xs font-medium text-muted">Logo web address<Input value={form.logoUrl} placeholder="https://..." onChange={field("logoUrl")} /></label>
          <label className="space-y-1 text-xs font-medium text-muted">Support email<Input value={form.supportEmail} onChange={field("supportEmail")} /></label>
          <label className="space-y-1 text-xs font-medium text-muted sm:col-span-2">Store web address (the Visit button)<Input value={form.storeUrl} placeholder="https://..." onChange={field("storeUrl")} /></label>
        </div>
        <Button disabled={busy !== null} onClick={() => run("look", async () => { await saveSettings(form); return "Saved. The previews above use the new look after a reload."; })}>Save</Button>
        <p className="text-xs text-muted">Only the owner can save these settings.</p>
      </CardContent>
    </Card>
  );
}

function TestSection({ busy, run }: { busy: string | null; run: Run }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Test mode</CardTitle>
        <CardDescription>Try everything without real customers. Sample customers use your SENDER_EMAIL with +mock1, +mock2... added, so their emails reach your own inbox.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={busy !== null} onClick={() => run("mock", async () => { const r = await loadSampleData(); return r.created ? `Added ${r.created} sample items (5 customers, 4 products, orders, one COD order).` : "The sample data is already there."; })}>
          Load sample customers and orders
        </Button>
        <Button variant="secondary" disabled={busy !== null} onClick={() => run("test", async () => { const r = await sendTestEmails(); return r.testMode ? "Test mode: the 4 test emails were prepared but not sent (add BREVO_API_KEY and SENDER_EMAIL)." : `Sent ${r.results.filter((x) => x.status === "sent").length} of ${r.results.length} test emails to your SENDER_EMAIL.`; })}>
          Send me a test of every email
        </Button>
      </CardContent>
    </Card>
  );
}
