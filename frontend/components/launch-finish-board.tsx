"use client";

import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, Link2, Loader2, Repeat, Rocket, Search, ShoppingBag, Trash2, TrendingDown, TrendingUp, Undo2, Users, Wallet } from "lucide-react";
import { KpiCard } from "@/components/kpi-card";
import { LaunchStepFrame } from "@/components/launch-step-frame";
import { Money } from "@/components/money";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getResults, linkProduct, listLinked, markLaunched, searchProductNames, unlinkProduct, type Results } from "@/lib/api/launch-steps";
import { updateProject, type Project } from "@/lib/api/launch";
import { ApiError } from "@/lib/api/config";
import { useLanguage } from "@/lib/i18n";
import { formatDate, formatNumber, formatPercent } from "@/lib/utils";

const field = "space-y-1 text-xs font-medium text-muted";
const today = () => new Date().toISOString().slice(0, 10);

/**
 * Step 6: mark the product as launched, tell the app which product names in your orders belong to it, and see
 * the real results from your own orders. Real profit is the Step 5 costs applied to real orders, so it is an
 * estimate; rates need enough orders of known outcome, otherwise they say "Not enough data yet".
 */
export function LaunchFinishBoard() {
  return <LaunchStepFrame step={6}>{(project, reload) => <FinishStep key={project.id} project={project} reload={reload} />}</LaunchStepFrame>;
}

function FinishStep({ project, reload }: { project: Project; reload: () => void }) {
  const { t, tf } = useLanguage();
  const [date, setDate] = useState(project.launchedOn ?? today());
  const [linked, setLinked] = useState<{ id: number; name: string }[]>([]);
  const [results, setResults] = useState<Results | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    listLinked(project.id).then(setLinked).catch(() => undefined);
    getResults(project.id).then(setResults).catch(() => setError(t("Something went wrong. Please try again.")));
  }, [project.id, t]);
  useEffect(() => {
    load();
  }, [load, project.launchedOn]);

  async function launch() {
    setError(null);
    setBusy(true);
    try {
      await markLaunched(project.id, date);
      reload();
      load();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    try {
      await updateProject(project.id, { status: "ready" });
      reload();
    } catch {
      setError(t("Something went wrong. Please try again."));
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Rocket className="h-4 w-4 text-accent" aria-hidden="true" />{project.launchedOn ? t("Launched") : t("Ready to launch?")}</CardTitle>
          <CardDescription>
            {project.launchedOn ? tf("{product} was launched on {date}.", { product: project.productName, date: formatDate(project.launchedOn) }) : t("Mark the product as launched on the day it went on sale. Results are counted from that day.")}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <label className={field}>{t("Launch date")}<Input type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} /></label>
          <Button onClick={launch} disabled={busy || !date}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Rocket className="h-4 w-4" aria-hidden="true" />}
            {project.launchedOn ? t("Change the launch date") : t("Mark as launched")}
          </Button>
          {project.launchedOn && project.status === "launched" ? <Button variant="ghost" onClick={undo}>{t("Move back to Ready")}</Button> : null}
        </CardContent>
      </Card>
      <div aria-live="polite">{error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}</div>

      <LinkProducts project={project} linked={linked} onChanged={load} />

      {results ? <ResultsView results={results} /> : null}
      {results && !results.reason ? null : results ? (
        <p className="text-sm text-muted">
          {results.reason === "not_launched" ? t("Mark the product as launched to see real results.") : t("Link at least one product name from your orders to see real results.")}
        </p>
      ) : null}
    </div>
  );
}

function LinkProducts({ project, linked, onChanged }: { project: Project; linked: { id: number; name: string }[]; onChanged: () => void }) {
  const { t } = useLanguage();
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<string[]>([]);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (query.trim().length < 2) return setError(t("Type at least 2 letters."));
    try {
      setMatches((await searchProductNames(query.trim())).map((m) => m.name));
      setSearched(true);
    } catch {
      setError(t("Something went wrong. Please try again."));
    }
  }

  async function add(name: string) {
    try {
      await linkProduct(project.id, name);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Link2 className="h-4 w-4 text-accent" aria-hidden="true" />{t("Products in your orders")}</CardTitle>
        <CardDescription>{t("Tell the app which product names in your orders belong to this launch. Orders are matched by name.")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {linked.length > 0 ? (
          <ul className="flex flex-wrap gap-2" aria-label={t("Linked products")}>
            {linked.map((l) => (
              <li key={l.id} className="inline-flex items-center gap-1 rounded-full border border-line bg-surface-3 py-1 pl-3 pr-1 text-sm text-ink">
                {l.name}
                <button type="button" aria-label={`${t("Unlink")} ${l.name}`} className="rounded-full p-1 text-muted hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
                  onClick={async () => { await unlinkProduct(project.id, l.id).catch(() => undefined); onChanged(); }}>
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted">{t("No product linked yet.")}</p>}
        <form onSubmit={search} className="flex flex-col gap-3 sm:flex-row sm:items-end" noValidate>
          <label className={`${field} flex-1`}>{t("Search your product names")}<Input value={query} onChange={(e) => setQuery(e.target.value)} maxLength={60} placeholder={project.productName} /></label>
          <Button type="submit" variant="secondary"><Search className="h-4 w-4" aria-hidden="true" />{t("Search")}</Button>
        </form>
        <div aria-live="polite">{error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}</div>
        {searched && matches.length === 0 ? (
          <div className="space-y-2">
            <p className="text-sm text-muted">{t("No product name in your orders or sales matches. You can still link the name exactly as you will type it on orders.")}</p>
            <Button variant="secondary" onClick={() => add(query.trim())}>{t("Link this name anyway")}</Button>
          </div>
        ) : null}
        {matches.length > 0 ? (
          <ul className="flex flex-wrap gap-2" aria-label={t("Matches")}>
            {matches.map((m) => (
              <li key={m}><Button variant="secondary" onClick={() => add(m)}>{m}</Button></li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ResultsView({ results }: { results: Results }) {
  const { t, tf } = useLanguage();
  if (results.reason) return null;
  const notEnough = (needed: number) => `${t("Not enough data yet")} ${tf("({n} more orders with a known result needed)", { n: needed })}`;
  const better = results.realProfitPerOrder !== null && results.expectedProfitPerOrder !== null && results.realProfitPerOrder >= results.expectedProfitPerOrder;
  return (
    <>
      <section aria-label={t("Real results")} className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Orders" value={formatNumber(results.orders)} delta={null} note={tf("Since {date}", { date: formatDate(results.launchedOn ?? "") })} icon={ShoppingBag} />
        <KpiCard label="Revenue" value={<Money value={results.revenue} />} delta={null} note={t("Value of the orders that include this product")} icon={Wallet} />
        <KpiCard label="Return rate" value={results.returnRate === null ? null : formatPercent(results.returnRate * 100, 0)} delta={null}
          unavailableReason={notEnough(results.returnNeeded)} note={tf("{n} orders with a known result", { n: results.closedOrders })} icon={Undo2} />
        <KpiCard label="Repeat buyers" value={formatNumber(results.repeatBuyers)} delta={null} note={tf("of {n} customers", { n: results.customers })} icon={Repeat} />
      </section>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Users className="h-4 w-4 text-accent" aria-hidden="true" />{t("Real profit compared with your estimate")}</CardTitle>
          <CardDescription>{t("Your Step 5 costs applied to your real orders. One piece per order is assumed, so this is an estimate.")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-ink-2">
          {!results.hasProfitInputs ? <p className="text-muted">{t("Save your numbers in the Profit check step to compare.")}</p>
            : results.realProfitPerOrder === null ? <p className="text-muted">{notEnough(results.returnNeeded)}</p> : (
              <>
                <p>{t("Estimate in Step 5, per order placed")}: <strong className="text-ink"><Money value={results.expectedProfitPerOrder ?? 0} /></strong></p>
                <p>{t("Real orders so far, per order placed")}: <strong className="text-ink"><Money value={results.realProfitPerOrder} /></strong></p>
                <p className={`inline-flex items-center gap-1.5 font-medium ${better ? "text-success" : "text-warning"}`}>
                  {better ? <TrendingUp className="h-4 w-4" aria-hidden="true" /> : <TrendingDown className="h-4 w-4" aria-hidden="true" />}
                  {better ? t("Doing as well as or better than the estimate.") : t("Doing worse than the estimate.")}
                </p>
                <p className="flex items-center gap-1.5 text-xs text-muted"><BadgeCheck className="h-3.5 w-3.5" aria-hidden="true" />{t("Before ad spend.")}</p>
              </>
            )}
        </CardContent>
      </Card>
    </>
  );
}
