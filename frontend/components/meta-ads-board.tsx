"use client";

import { useEffect, useRef, useState } from "react";
import { FlaskConical, Loader2, Upload } from "lucide-react";
import { Money } from "@/components/money";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { API_MODE, ApiError } from "@/lib/api/config";
import { getRoas, importSpend, metaEventSummary, metaStatus, previewAudience, pushAudience, sendMetaEvents, syncSpend, type AudienceResult, type MetaStatus, type Roas } from "@/lib/api/meta-ads";
import { fmt } from "@/lib/format";

const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Meta Ads: audiences from customers who agreed, delivered-only purchase events, and Meta's claims next to your real delivered revenue. */
export function MetaAdsBoard() {
  if (API_MODE !== "live") return <p className="text-sm text-muted">Meta Ads needs the backend. Connect it to use this page.</p>;
  return <MetaContent />;
}

function MetaContent() {
  const [status, setStatus] = useState<MetaStatus | null>(null);
  const [events, setEvents] = useState<Record<string, number>>({});
  const [roas, setRoas] = useState<Roas | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const [audience, setAudience] = useState<AudienceResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    const end = new Date();
    const start = new Date(end.getTime() - 29 * 86_400_000);
    Promise.all([metaStatus(), metaEventSummary(), getRoas(iso(start), iso(end))])
      .then(([s, e, r]) => !cancelled && (setStatus(s), setEvents(e), setRoas(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [version]);

  async function run(name: string, work: () => Promise<string | void>) {
    setBusy(name);
    setNote(null);
    try {
      const message = await work();
      if (message) setNote(message);
      setVersion((v) => v + 1);
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(null);
    }
  }

  if (failed) return <ErrorState title="Could not load Meta Ads" description="Please check your connection and reload the page." />;
  if (!status || !roas) return <Skeleton className="h-64 w-full" />;
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">Connection
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${status.testMode ? "bg-warning/15 text-warning" : "bg-success/15 text-success"}`}>{status.testMode ? <><FlaskConical className="h-3 w-3" aria-hidden="true" />Test mode: nothing is sent to Meta</> : "Live"}</span>
          </CardTitle>
          <CardDescription>{Object.entries(status.connected).map(([k, v]) => `${k}: ${v ? "set" : "missing"}`).join(" · ")}</CardDescription>
        </CardHeader>
        <CardContent><ol className="list-decimal space-y-1 pl-5 text-sm text-ink-2">{status.setupSteps.map((s) => <li key={s}>{s}</li>)}</ol></CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Custom Audiences</CardTitle><CardDescription>Only customers who agreed to WhatsApp or email are included, and only as SHA-256 hashes.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {Object.entries(status.segments).map(([k, label]) => (
              <span key={k} className="flex gap-1">
                <Button variant="secondary" disabled={busy !== null} onClick={() => run(`p${k}`, async () => { setAudience(await previewAudience(k)); })}>Preview: {label}</Button>
              </span>
            ))}
          </div>
          {audience ? (
            <div className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
              <p className="text-ink">{fmt("{n} customers would be sent; {m} left out (never agreed or no email/phone).", { n: audience.customers, m: audience.leftOut })}</p>
              {audience.sample.length ? <p className="mt-1 break-all text-xs text-muted">Example (hashed): {audience.sample[0].join(" | ")}</p> : null}
              <Button className="mt-2" disabled={busy !== null || audience.customers === 0} onClick={() => { if (window.confirm("This shares hashed customer details with Meta (nothing is sent in test mode). Continue?")) void run("push", async () => { const r = await pushAudience(audience.segment, ""); return r.dryRun ? "Test mode: the audience was prepared but nothing was sent." : `${"Audience created"}: ${r.audienceId}`; }); }}>
                {busy === "push" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}{status.testMode ? "Prepare (test mode)" : "Send to Meta (owner)"}
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Purchase events (delivered orders only)</CardTitle><CardDescription>An event is made when a COD order is delivered, not when it is placed, so Meta learns from customers who really paid.</CardDescription></CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3 text-sm text-ink-2">
          <span>{["pending", "sent", "dry_run", "failed", "skipped"].map((k) => `${k.replace("_", " ")}: ${events[k] ?? 0}`).join(" · ")}</span>
          <Button variant="secondary" disabled={busy !== null} onClick={() => run("send", async () => { const r = await sendMetaEvents(); return JSON.stringify(r); })}>Send due events (owner)</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Ad spend</CardTitle><CardDescription>{"Import Meta's CSV export (columns: date, campaign, channel, amount, purchases, purchase value), or read it from the Marketing API."}</CardDescription></CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <input ref={file} type="file" accept=".csv" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void run("import", async () => { const r = await importSpend(f); return fmt("{a} added, {u} updated, {r} rejected.", { a: r.added, u: r.updated, r: r.rejected }) + (r.errors[0] ? ` ${r.errors[0]}` : ""); }); e.target.value = ""; }} />
          <Button variant="secondary" disabled={busy !== null} onClick={() => file.current?.click()}><Upload className="h-4 w-4" aria-hidden="true" />Import CSV</Button>
          <Button variant="secondary" disabled={busy !== null} onClick={() => run("sync", async () => fmt("{n} rows read from Meta.", { n: (await syncSpend()).rows }))}>Read from Meta (owner)</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>True ROAS, last 30 days</CardTitle><CardDescription>{roas.note}</CardDescription></CardHeader>
        <CardContent className="space-y-2">
          {roas.campaigns.length === 0 ? <p className="text-sm text-muted">No ad spend yet.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[40rem] text-left text-sm">
                <thead className="text-xs text-muted"><tr><th className="py-1 pr-3 font-medium">Campaign</th><th className="px-2 font-medium">Spend</th><th className="px-2 font-medium">Meta says (revenue)</th><th className="px-2 font-medium">Really delivered</th><th className="px-2 font-medium">Meta ROAS</th><th className="px-2 font-medium">True ROAS</th><th className="px-2 font-medium">Cost per delivered order</th></tr></thead>
                <tbody className="text-ink-2">
                  {roas.campaigns.map((c) => (
                    <tr key={c.campaign} className="border-t border-line">
                      <td className="py-1.5 pr-3 text-ink">{c.campaign}</td><td className="px-2"><Money value={c.spend} /></td>
                      <td className="px-2">{c.metaRevenue === null ? "-" : <Money value={c.metaRevenue} />}</td>
                      <td className="px-2"><Money value={c.realRevenue} /> ({c.delivered}/{c.orders})</td>
                      <td className="px-2">{c.metaRoas === null ? "-" : `${c.metaRoas.toFixed(2)}x`}</td>
                      <td className="px-2">{c.trueRoas === null ? <span className="text-xs text-muted">Not enough data yet</span> : `${c.trueRoas.toFixed(2)}x`}</td>
                      <td className="px-2">{c.costPerDeliveredOrder === null ? "-" : <Money value={c.costPerDeliveredOrder} />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-muted">{fmt("{n} orders in this period carry no campaign tag, so they cannot be matched. A true ratio needs at least {min} delivered orders per campaign.", { n: roas.untaggedOrders, min: roas.minGroupCount })}</p>
        </CardContent>
      </Card>
      <div aria-live="polite">{note ? <p className="text-sm text-ink-2">{note}</p> : null}</div>
    </div>
  );
}
