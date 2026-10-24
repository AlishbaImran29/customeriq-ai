"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Clock, Download, Loader2, Minus, Plus, RefreshCw, Rocket, Sparkles, Trash2, TrendingDown, TrendingUp, Upload } from "lucide-react";
import { LaunchSteps } from "@/components/launch-steps";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/config";
import {
  LAUNCH_AVAILABLE, MAX_TREND_BYTES, askForIdeas, createProject, deleteTrend, getGrowth, listTrends, uploadTrend,
  type Growth, type Ideas, type Trend, type TrendLabel,
} from "@/lib/api/launch";
import { useLanguage } from "@/lib/i18n";
import { formatDate, formatNumber, formatPercent } from "@/lib/utils";

const LINE = "#22d3ee";
const GRID = "#263449";
const AXIS_TICK = { fontSize: 12, fill: "#94a3b8" };

const LABEL_LOOK: Record<TrendLabel, { text: string; icon: typeof Minus; className: string }> = {
  rising: { text: "Rising", icon: TrendingUp, className: "bg-success/10 text-success" },
  stable: { text: "Stable", icon: Minus, className: "bg-surface-3 text-ink-2" },
  falling: { text: "Falling", icon: TrendingDown, className: "bg-warning/10 text-warning" },
};

/**
 * Step 1 of Launch Studio. Three sources of ideas, all from data the seller owns or exports:
 * a Google Trends CSV they download themselves (the app never contacts Google), their own fastest-growing
 * products, and an AI suggestion built from those two. The AI text is editable and nothing is used until the seller accepts it.
 */
export function TrendFinderBoard() {
  const { t } = useLanguage();
  const [trends, setTrends] = useState<Trend[] | null>(null);

  const load = useCallback(() => {
    listTrends().then(setTrends).catch(() => setTrends([]));
  }, []);

  useEffect(() => {
    if (LAUNCH_AVAILABLE) load();
  }, [load]);

  if (!LAUNCH_AVAILABLE) {
    return (
      <EmptyState
        icon={Rocket}
        title={t("Launch Studio needs the backend")}
        description={t("Launch projects are saved in your database. Connect the backend to use Launch Studio.")}
      />
    );
  }

  return (
    <div className="space-y-5">
      <LaunchSteps current={1} />
      <HelpCard />
      <UploadCard onUploaded={load} />
      {trends && trends.length > 0 ? (
        <section aria-label={t("Your trends")} className="space-y-4">
          {trends.map((tr) => <TrendCard key={tr.id} trend={tr} onDeleted={load} />)}
        </section>
      ) : null}
      <GrowthCard />
      <IdeasCard hasTrends={!!trends && trends.length > 0} />
    </div>
  );
}

function HelpCard() {
  const { t } = useLanguage();
  return (
    <details className="rounded-2xl border border-line bg-surface p-4 text-sm text-ink-2">
      <summary className="cursor-pointer rounded font-medium text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40">
        {t("How to download a file from Google Trends")}
      </summary>
      <ol className="mt-3 list-decimal space-y-1.5 pl-5">
        <li>{t("Open trends.google.com and type the product you are curious about, for example \"neck fan\".")}</li>
        <li>{t("Set the region to Pakistan and the time to \"Past 12 months\" (or longer).")}</li>
        <li>{t("On the \"Interest over time\" chart click the small download arrow at the top right. A .csv file is saved.")}</li>
        <li>{t("Do the same with the download arrow in the \"Related queries\" box to get the words people also search.")}</li>
        <li>{t("Upload the file below. The app never contacts Google: it only reads the file you give it.")}</li>
      </ol>
      <p className="mt-3 text-xs text-muted">{t("Google Trends numbers run from 0 to 100 (100 is the most popular moment in your file). They show interest in searching, not how many people buy.")}</p>
    </details>
  );
}

function UploadCard({ onUploaded }: { onUploaded: () => void }) {
  const { t, tf } = useLanguage();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function send(file: File | undefined) {
    if (!file) return;
    setError(null);
    setDone(null);
    if (file.size > MAX_TREND_BYTES) return setError(t("The file is larger than 2 MB. A Google Trends export is much smaller than that."));
    setBusy(true);
    try {
      const saved = await uploadTrend(file);
      setDone(tf("{count} trend saved.", { count: saved.length }));
      onUploaded();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Upload a Google Trends file")}</CardTitle>
        <CardDescription>{t("Interest over time or related queries, as downloaded from Google Trends.")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <input ref={input} type="file" accept=".csv,text/csv" className="sr-only" id="trend-file" onChange={(e) => send(e.target.files?.[0])} />
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={busy} onClick={() => input.current?.click()}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />}
            {t("Upload CSV")}
          </Button>
          <a href="/google_trends_sample_template.csv" download className="inline-flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3.5 py-2 text-sm font-medium text-ink-2 hover:bg-surface-3 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
            <Download className="h-4 w-4" aria-hidden="true" />
            {t("Download a sample file")}
          </a>
        </div>
        <p className="text-xs text-muted">{t("The sample file is made-up data in the same format Google uses. Use it to try the page; it is not real search data.")}</p>
        <div aria-live="polite">
          {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
          {done ? <p className="text-sm text-success">{done}</p> : null}
        </div>
      </CardContent>
    </Card>
  );
}

function TrendCard({ trend, onDeleted }: { trend: Trend; onDeleted: () => void }) {
  const { t, tf } = useLanguage();
  const look = trend.label ? LABEL_LOOK[trend.label] : null;
  const Icon = look?.icon ?? Clock;
  async function remove() {
    await deleteTrend(trend.id).catch(() => undefined);
    onDeleted();
  }
  const top = trend.related.filter((r) => r.kind === "top");
  const rising = trend.related.filter((r) => r.kind === "rising");
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>{trend.keyword}</CardTitle>
          <CardDescription>
            {trend.region ? `${trend.region} · ` : ""}
            {tf("Uploaded {date}", { date: formatDate(trend.createdAt.slice(0, 10)) })}
          </CardDescription>
        </div>
        <Button variant="ghost" onClick={remove} aria-label={tf("Remove {product}", { product: trend.keyword })}>
          <Trash2 className="h-4 w-4" aria-hidden="true" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {trend.points.length > 0 ? (
          <>
            <p className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${look?.className ?? "bg-surface-3 text-muted"}`}>
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              {look ? t(look.text) : t("Not enough data yet")}
            </p>
            <p className="text-xs text-muted">
              {trend.label && trend.ratio !== null
                ? tf("The last 4 weeks averaged {ratio} of the 8 weeks before them (rising is 115% or more, falling is 85% or less). This describes the past, it is not a forecast.", { ratio: formatPercent(trend.ratio * 100, 0) })
                : t("A label needs at least 12 weeks of weekly or daily data. Download a longer period from Google Trends.")}
            </p>
            <div role="img" aria-label={tf("Line chart of search interest for {product}", { product: trend.keyword })} className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend.points} margin={{ left: 0, right: 12 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="date" tick={AXIS_TICK} minTickGap={32} tickFormatter={(d: string) => d.slice(0, 7)} />
                  <YAxis domain={[0, 100]} tick={AXIS_TICK} width={32} />
                  <Tooltip labelFormatter={(d) => formatDate(String(d))} />
                  <Line type="monotone" dataKey="value" name={t("Interest (0-100)")} stroke={LINE} dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </>
        ) : null}
        {trend.related.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <RelatedList title={t("Top related searches")} items={top} />
            <RelatedList title={t("Rising related searches")} items={rising} />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function RelatedList({ title, items }: { title: string; items: Trend["related"] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-medium text-muted">{title}</p>
      <ul className="mt-1 space-y-1 text-sm text-ink-2">
        {items.slice(0, 8).map((r) => (
          <li key={`${r.kind}-${r.query}`} className="flex justify-between gap-3">
            <span>{r.query}</span>
            <span className="tabular-nums text-muted">{r.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function GrowthCard() {
  const { t, tf } = useLanguage();
  const [days, setDays] = useState<30 | 90>(30);
  const [data, setData] = useState<Growth | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getGrowth(days)
      .then((d) => !cancelled && (setData(d), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [days]);

  const unit = data?.metric === "orders" ? t("orders") : t("units");
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Your fastest-growing products")}</CardTitle>
        <CardDescription>{tf("Sales in the last {days} days compared with the {days} days before.", { days })}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <FilterPills
          label={t("Filter by period")}
          value={String(days)}
          onChange={(v) => setDays(Number(v) as 30 | 90)}
          options={[{ value: "30", label: t("Last 30 days") }, { value: "90", label: t("Last 90 days") }]}
        />
        {failed ? <p role="alert" className="text-sm text-danger">{t("Could not load your product growth.")}</p> : null}
        {data?.source === "demo" ? <p className="text-xs text-warning">{t("Demo data (synthetic).")}</p> : null}
        {data && data.reason ? (
          <p className="text-sm text-muted">
            {data.reason === "no_data"
              ? t("No product names found yet. Add orders with products (Add Order, WhatsApp chat or your own sheet) or import product sales.")
              : t("Not enough history yet to compare two periods.")}
          </p>
        ) : null}
        {data && !data.reason ? (
          data.rows.length === 0 ? (
            <p className="text-sm text-muted">
              {tf("No product has at least {minimum} sales in these two periods and grew. A product needs that many before it is compared.", { minimum: data.minGroupCount })}
            </p>
          ) : (
            <div>
              <table className="w-full text-left text-sm">
                <caption className="sr-only">{t("Your fastest-growing products")}</caption>
                <thead className="text-xs text-muted">
                  <tr className="border-b border-line">
                    <th scope="col" className="py-2 pr-3 font-medium">{t("Product")}</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">{tf("Last {days} days ({unit})", { days, unit })}</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">{t("Before")}</th>
                    <th scope="col" className="py-2 font-medium">{t("Growth")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r) => (
                    <tr key={r.product} className="border-b border-line/60">
                      <td className="py-2.5 pr-3 font-medium text-ink">{r.product}</td>
                      <td className="py-2.5 pr-3 text-right tabular-nums">{formatNumber(r.last)}</td>
                      <td className="py-2.5 pr-3 text-right tabular-nums">{formatNumber(r.before)}</td>
                      <td className="py-2.5">
                        <span className="inline-flex items-center gap-1.5 text-success">
                          <TrendingUp className="h-4 w-4" aria-hidden="true" />
                          {r.growth === null ? t("New") : `+${formatPercent(r.growth * 100, 0)}`}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : null}
        {data && data.tooSmall > 0 ? (
          <p className="text-xs text-muted">{tf("{count} products have too few sales to compare (Not enough data yet).", { count: data.tooSmall })}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function IdeasCard({ hasTrends }: { hasTrends: boolean }) {
  const { t, tf } = useLanguage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ideas, setIdeas] = useState<Ideas | null>(null);
  const [names, setNames] = useState<string[]>([]);
  const [created, setCreated] = useState<Record<number, boolean>>({});

  async function ask(force: boolean) {
    setBusy(true);
    setError(null);
    setCreated({});
    try {
      const result = await askForIdeas(force);
      setIdeas(result);
      setNames(result.ideas.map((i) => i.name));
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  async function accept(index: number) {
    const name = names[index]?.trim();
    if (!name || name.length < 2) return setError(t("Give the product a name of at least 2 characters."));
    try {
      await createProject({ productName: name, notes: ideas?.ideas[index]?.reason });
      setCreated((c) => ({ ...c, [index]: true }));
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-accent" aria-hidden="true" />{t("Ask AI for ideas")}</CardTitle>
        <CardDescription>
          {hasTrends
            ? t("The AI reads your trend results and your shop's categories and suggests 5 products. It can be wrong: you decide.")
            : t("Upload a Google Trends file first (or import some orders), so the AI has facts to work from.")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => ask(false)} disabled={busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}
            {t("Ask AI for ideas")}
          </Button>
          {ideas ? (
            <Button variant="secondary" onClick={() => ask(true)} disabled={busy}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              {t("Ask again")}
            </Button>
          ) : null}
        </div>
        <div aria-live="polite">{error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}</div>
        {ideas ? (
          <div className="space-y-3">
            <p className="text-xs text-muted">
              <span className="rounded-full bg-accent/10 px-2 py-0.5 font-medium text-accent">{t("AI suggestion")}</span>{" "}
              {ideas.cached ? t("Saved answer: no new AI call was made.") : ideas.model ? tf("Written by {model}.", { model: ideas.model }) : ""}
            </p>
            <ul className="space-y-3">
              {ideas.ideas.map((idea, i) => (
                <li key={i} className="rounded-xl border border-line bg-surface-2 p-3">
                  <label className="block space-y-1 text-xs font-medium text-muted">
                    {t("Product idea (you can change it)")}
                    <Input value={names[i] ?? ""} onChange={(e) => setNames((all) => all.map((n, j) => (j === i ? e.target.value : n)))} maxLength={120} />
                  </label>
                  <p className="mt-2 text-sm text-ink-2">{idea.reason}</p>
                  <div className="mt-2">
                    {created[i] ? (
                      <Link href="/launch" className="text-sm font-medium text-accent underline underline-offset-2">{t("Project created. See your launch projects")}</Link>
                    ) : (
                      <Button variant="secondary" onClick={() => accept(i)}>
                        <Plus className="h-4 w-4" aria-hidden="true" />
                        {t("Create launch project")}
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
