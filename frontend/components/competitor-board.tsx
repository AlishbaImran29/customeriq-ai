"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CircleCheck, CircleX, ExternalLink, ImageUp, Loader2, Plus, RefreshCw, Search, Sparkles, Trash2 } from "lucide-react";
import { LaunchStepFrame } from "@/components/launch-step-frame";
import { Money } from "@/components/money";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { adLibraryLink, analyseAds, listAds, removeAd, saveAd, type Ad, type AdAnalysis } from "@/lib/api/launch-steps";
import { ApiError } from "@/lib/api/config";
import type { Project } from "@/lib/api/launch";
import { formatDate } from "@/lib/utils";
import { fmt } from "@/lib/format";

const field = "space-y-1 text-xs font-medium text-muted";
const areaClass =
  "min-h-24 w-full rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-faint outline-none transition focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";
const MAX_IMAGE_BYTES = 3 * 1024 * 1024;

const HOOKS: Record<string, string> = {
  question: "Question", problem: "Problem", discount: "Discount", social_proof: "Social proof", urgency: "Urgency",
  benefit: "Benefit", curiosity: "Curiosity", other: "Other",
};
const LANGS: Record<string, string> = { urdu: "Urdu", roman_urdu: "Roman Urdu", english: "English", mixed: "Mixed", other: "Other" };

/**
 * Step 3. The seller looks at competitor ads on the Meta Ad Library WEBSITE and saves the ones they want.
 * The app only builds the link: the official Ad Library API does not return commercial ads outside the EU,
 * and scraping the site is not allowed.
 */
export function CompetitorBoard() {
  return <LaunchStepFrame step={3}>{(project) => <CompetitorStep key={project.id} project={project} />}</LaunchStepFrame>;
}

function CompetitorStep({ project }: { project: Project }) {
  const [ads, setAds] = useState<Ad[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    listAds(project.id).then(setAds).catch(() => setError("Something went wrong. Please try again."));
  }, [project.id]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-5">
      <div aria-live="polite">{error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}</div>
      <LibraryCard project={project} />
      <SaveAdCard project={project} onSaved={load} />
      <AdList ads={ads} onDeleted={load} />
      <AnalysisCard project={project} adCount={ads?.length ?? 0} ads={ads ?? []} />
    </div>
  );
}

function LibraryCard({ project }: { project: Project }) {
  const [keyword, setKeyword] = useState(project.productName);
  const [error, setError] = useState<string | null>(null);

  async function open(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (keyword.trim().length < 2) return setError("Type a keyword of at least 2 letters.");
    try {
      const { url } = await adLibraryLink(keyword.trim());
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Find competitor ads</CardTitle>
        <CardDescription>This opens the Meta Ad Library website for Pakistan with your keyword already typed. Look at the ads there, then save the ones you want below.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={open} className="flex flex-col gap-3 sm:flex-row sm:items-end" noValidate>
          <label className={`${field} flex-1`}>Keyword<Input value={keyword} onChange={(e) => setKeyword(e.target.value)} maxLength={100} /></label>
          <Button type="submit"><Search className="h-4 w-4" aria-hidden="true" />Open Meta Ad Library<ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /></Button>
        </form>
        <div aria-live="polite">{error ? <p role="alert" className="mt-2 text-sm text-danger">{error}</p> : null}</div>
        <p className="mt-3 text-xs text-muted">The app does not copy ads from Facebook for you: that is not allowed. You choose what to save.</p>
      </CardContent>
    </Card>
  );
}

function SaveAdCard({ project, onSaved }: { project: Project; onSaved: () => void }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [pageName, setPageName] = useState("");
  const [text, setText] = useState("");
  const [link, setLink] = useState("");
  const [price, setPrice] = useState("");
  const [offer, setOffer] = useState("");
  const [seen, setSeen] = useState(new Date().toISOString().slice(0, 10));
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (pageName.trim().length < 2) return setError("Write the name of the page that ran the ad.");
    if (file && file.size > MAX_IMAGE_BYTES) return setError("The screenshot is larger than 3 MB. Use a smaller picture.");
    const form = new FormData();
    form.append("page_name", pageName.trim());
    if (text.trim()) form.append("ad_text", text.trim());
    if (link.trim()) form.append("link", link.trim());
    if (price.trim()) form.append("price_seen", price.replace(/,/g, ""));
    if (offer.trim()) form.append("offer_seen", offer.trim());
    if (seen) form.append("date_seen", seen);
    if (file) form.append("screenshot", file);
    setBusy(true);
    try {
      await saveAd(project.id, form);
      setPageName(""); setText(""); setLink(""); setPrice(""); setOffer(""); setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Save a competitor ad</CardTitle>
        <CardDescription>Paste what you saw. Only the page name is required; the more you add, the better the analysis.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2" noValidate>
          <label className={field}>Page name<Input value={pageName} onChange={(e) => setPageName(e.target.value)} maxLength={160} /></label>
          <label className={field}>Date seen<Input type="date" value={seen} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setSeen(e.target.value)} /></label>
          <label className={`${field} sm:col-span-2`}>Ad text (paste it)<textarea className={areaClass} value={text} onChange={(e) => setText(e.target.value)} maxLength={5000} dir="auto" /></label>
          <label className={field}>Price seen (PKR)<Input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} /></label>
          <label className={field}>Offer seen<Input value={offer} onChange={(e) => setOffer(e.target.value)} maxLength={300} placeholder="for example: free delivery" /></label>
          <label className={`${field} sm:col-span-2`}>Link to the ad (optional)<Input value={link} onChange={(e) => setLink(e.target.value)} maxLength={500} inputMode="url" placeholder="https://" /></label>
          <div className="sm:col-span-2">
            <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" id="ad-screenshot" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <Button type="button" variant="secondary" onClick={() => fileInput.current?.click()}>
              <ImageUp className="h-4 w-4" aria-hidden="true" />{file ? file.name : "Add a screenshot (optional)"}
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-3 sm:col-span-2" aria-live="polite">
            <Button type="submit" disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}Save ad</Button>
            {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function AdList({ ads, onDeleted }: { ads: Ad[] | null; onDeleted: () => void }) {
  if (!ads || ads.length === 0) return <p className="text-sm text-muted">No ads saved yet.</p>;
  return (
    <section aria-label="Saved ads" className="space-y-3">
      <h2 className="text-base font-semibold text-ink">{fmt("Saved ads ({count})", { count: ads.length })}</h2>
      <ul className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {ads.map((ad) => (
          <li key={ad.id}>
            <Card className="h-full">
              <CardContent className="space-y-2 pt-5 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium text-ink">{ad.pageName}</p>
                    <p className="text-xs text-muted">{fmt("Seen {date}", { date: formatDate(ad.dateSeen) })}</p>
                  </div>
                  <Button variant="ghost" aria-label={fmt("Delete {product}", { product: ad.pageName })}
                    onClick={async () => { await removeAd(ad.id).catch(() => undefined); onDeleted(); }}>
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
                {ad.screenshotUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={ad.screenshotUrl} alt={fmt("Screenshot of the ad from {page}", { page: ad.pageName })} className="max-h-64 w-full rounded-lg border border-line object-contain" loading="lazy" />
                ) : ad.hasScreenshot ? <p className="text-xs text-muted">The screenshot could not be loaded.</p> : null}
                {ad.adText ? <p className="whitespace-pre-wrap text-ink-2" dir="auto">{ad.adText}</p> : null}
                <p className="text-xs text-ink-2">
                  {ad.priceSeen !== null ? <><Money value={ad.priceSeen} /> · </> : null}
                  {ad.offerSeen ?? ""}
                </p>
                {ad.link ? (
                  <a href={ad.link} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 text-xs font-medium text-accent underline underline-offset-2">
                    <ExternalLink className="h-3 w-3" aria-hidden="true" />Open the ad link
                  </a>
                ) : null}
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  );
}

function AnalysisCard({ project, adCount, ads }: { project: Project; adCount: number; ads: Ad[] }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AdAnalysis | null>(null);
  const names = new Map(ads.map((a) => [a.id, a.pageName]));

  async function run(force: boolean) {
    setBusy(true);
    setError(null);
    try {
      setResult(await analyseAds(project.id, force));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-accent" aria-hidden="true" />Analyse with AI</CardTitle>
        <CardDescription>The AI reads your saved ads and points out common patterns and gaps you can use. It can be wrong: check it against the ads.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => run(false)} disabled={busy || adCount === 0}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}
            Analyse with AI
          </Button>
          {result ? <Button variant="secondary" onClick={() => run(true)} disabled={busy}><RefreshCw className="h-4 w-4" aria-hidden="true" />Ask again</Button> : null}
        </div>
        {adCount === 0 ? <p className="text-xs text-muted">Save at least one ad first.</p> : null}
        <div aria-live="polite">{error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}</div>
        {result ? (
          <div className="space-y-4">
            <p className="text-xs text-muted">
              <span className="rounded-full bg-accent/10 px-2 py-0.5 font-medium text-accent">AI suggestion</span>{" "}
              {result.cached ? "Saved answer: no new AI call was made." : result.model ? fmt("Written by {model}.", { model: result.model }) : ""}
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              <SummaryList title="What the ads have in common" items={result.patterns} />
              <SummaryList title="Gaps you can use" items={result.gaps} />
            </div>
            <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {result.ads.map((f) => (
                <li key={f.id} className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
                  <p className="font-medium text-ink">{names.get(f.id) ?? `#${f.id}`}</p>
                  <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-ink-2">
                    <dt className="text-muted">Hook</dt><dd>{(HOOKS[f.hookType] ?? "Other")}</dd>
                    <dt className="text-muted">Offer</dt><dd>{f.offer ?? "-"}</dd>
                    <dt className="text-muted">Price</dt><dd>{f.price === null ? "-" : <Money value={f.price} />}</dd>
                    <dt className="text-muted">Call to action</dt><dd>{f.cta ?? "-"}</dd>
                    <dt className="text-muted">Cash on delivery</dt>
                    <dd className="inline-flex items-center gap-1.5">
                      {f.codMentioned ? <CircleCheck className="h-4 w-4 text-success" aria-hidden="true" /> : <CircleX className="h-4 w-4 text-muted" aria-hidden="true" />}
                      {f.codMentioned ? "Yes" : "No"}
                    </dd>
                    <dt className="text-muted">Language</dt><dd>{(LANGS[f.language] ?? "Other")}</dd>
                  </dl>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function SummaryList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="rounded-xl border border-line bg-surface-2 p-3">
      <p className="text-sm font-medium text-ink">{title}</p>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink-2">{items.map((i) => <li key={i}>{i}</li>)}</ul>
    </div>
  );
}
