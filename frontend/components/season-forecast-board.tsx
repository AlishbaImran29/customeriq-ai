"use client";

import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CalendarClock, CircleCheck, FlaskConical, Info, Minus, TrendingDown, TrendingUp } from "lucide-react";
import { SalesUpload } from "@/components/sales-upload";
import { EmptyState, ErrorState } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Skeleton } from "@/components/ui/skeleton";
import { SEASONS_AVAILABLE, getSeasonForecast, type Advice, type Season, type SeasonForecast } from "@/lib/api/seasons";
import { useLanguage } from "@/lib/i18n";
import { formatDate, formatNumber, formatPercent } from "@/lib/utils";

const SERIES_1 = "#22d3ee";
const SERIES_2 = "#a78bfa";
const GRID = "#263449";
const AXIS_TICK = { fontSize: 12, fill: "#94a3b8" };

const ADVICE: Record<Advice, { label: string; icon: typeof Minus; className: string }> = {
  stock_more: { label: "Stock more", icon: TrendingUp, className: "text-success" },
  similar: { label: "Similar", icon: Minus, className: "text-ink-2" },
  stock_less: { label: "Stock less", icon: TrendingDown, className: "text-warning" },
};

const REASONS: Record<string, string> = {
  too_early: "The forecast is made 4 weeks before the season starts. Until then this shows last year's sales.",
  not_better: "In past tests the model did not beat last year's sales, so no forecast is shown.",
  no_backtest: "There are not enough past seasons yet to test the model, so no forecast is shown.",
  few_products: "At least {minimum} products with sales last year are needed.",
  no_last_year: "Sales for the whole of this season last year are needed.",
  no_target: "No coming season is listed in the season dates file.",
};

/**
 * The Season Forecast. A forecast is shown for a season only when the model beat last year's sales in
 * back-tests on held-out seasons (the backend decides). Otherwise the page shows last year's sales or
 * "Not enough data yet", with both scores and the reason. Ranges are estimates and are labelled so.
 */
export function SeasonForecastBoard() {
  const { t } = useLanguage();
  const [data, setData] = useState<SeasonForecast | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [chosen, setChosen] = useState<string | null>(null);

  useEffect(() => {
    if (!SEASONS_AVAILABLE) return;
    let cancelled = false;
    getSeasonForecast()
      .then((d) => !cancelled && (setData(d), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (!SEASONS_AVAILABLE) {
    return (
      <EmptyState
        icon={CalendarClock}
        title={t("The Season Forecast needs your own sales")}
        description={t("There is no sample data for this page, because made-up forecasts would be misleading. Connect the backend and import your product sales to see it.")}
      />
    );
  }
  if (failed) return <ErrorState title={t("Could not load the Season Forecast")} description={t("Please check your connection and reload the page.")} />;
  if (!data) return <Skeleton className="h-64 w-full" />;

  const empty = data.realWeeks + data.demoWeeks === 0;
  const season = data.seasons.find((s) => s.id === chosen) ?? data.seasons.find((s) => s.status === "forecast") ?? data.seasons[0];

  return (
    <div className="space-y-5">
      {data.sourceUsed === "demo" && !empty ? (
        <div role="status" className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-ink">
          <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
          <p>
            <strong>{t("Demo data (synthetic).")}</strong>{" "}
            {t("These sales are made up to show how the page works. They are not real results.")}
          </p>
        </div>
      ) : null}

      {empty || !season ? (
        <EmptyState
          icon={CalendarClock}
          title={t("No product sales yet")}
          description={t("Upload how many units of each product you sold, with dates, and the forecast will appear when there is enough history.")}
        />
      ) : (
        <>
          <FilterPills
            label={t("Choose a season")}
            value={season.id}
            onChange={setChosen}
            options={data.seasons.map((s) => ({ value: s.id, label: s.name }))}
          />
          <SeasonView season={season} minimum={data.minGroupCount} dataTo={data.dataTo} />
        </>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t("Product sales")}</CardTitle>
          <CardDescription>{t("The forecast learns from your past sales. More seasons of history make it testable.")}</CardDescription>
        </CardHeader>
        <CardContent><SalesUpload onChange={reload} /></CardContent>
      </Card>
    </div>
  );
}

function AdviceLabel({ advice }: { advice: Advice | null }) {
  const { t } = useLanguage();
  if (!advice) return <span className="text-muted">{t("Too few sales to advise")}</span>;
  const { label, icon: Icon, className } = ADVICE[advice];
  return (
    <span className={`inline-flex items-center gap-1.5 font-medium ${className}`}>
      <Icon className="h-4 w-4" aria-hidden="true" />
      {t(label)}
    </span>
  );
}

function BackTestScores({ season }: { season: Season }) {
  const { t, tf } = useLanguage();
  const b = season.backtest;
  if (b.cases === 0 || b.modelMae === null || b.baselineMae === null) {
    return <p className="text-xs text-muted">{t("No back-test yet: it needs earlier seasons to learn from and later ones to test on.")}</p>;
  }
  const units = (v: number) => formatNumber(Math.round(v * 10) / 10);
  const pct = (v: number | null) => (v === null ? "-" : formatPercent(v * 100, 0));
  return (
    <div className="rounded-xl border border-line bg-surface-2 p-3">
      <p className="text-xs font-medium text-muted">
        {tf("Back-test: {cases} past seasons ({years}), {rows} product forecasts compared", { cases: b.cases, years: b.tested.join(", "), rows: formatNumber(b.rows) })}
      </p>
      <table className="mt-2 w-full text-left text-sm">
        <caption className="sr-only">{t("Model compared with last year's sales")}</caption>
        <thead className="text-xs text-muted">
          <tr>
            <th scope="col" className="py-1 pr-3 font-medium"><span className="sr-only">{t("Score")}</span></th>
            <th scope="col" className="py-1 pr-3 text-right font-medium">{t("Model")}</th>
            <th scope="col" className="py-1 text-right font-medium">{t("Last year's sales")}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row" className="py-1 pr-3 font-medium text-ink-2">{t("Average error (units)")}</th>
            <td className="py-1 pr-3 text-right tabular-nums">{units(b.modelMae)}</td>
            <td className="py-1 text-right tabular-nums">{units(b.baselineMae)}</td>
          </tr>
          <tr>
            <th scope="row" className="py-1 pr-3 font-medium text-ink-2">{t("Average error (%)")}</th>
            <td className="py-1 pr-3 text-right tabular-nums">{pct(b.modelMape)}</td>
            <td className="py-1 text-right tabular-nums">{pct(b.baselineMape)}</td>
          </tr>
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted">
        {b.passed
          ? tf("The model is {gain} more accurate, and its percentage error is not worse, so its forecast can be shown.", { gain: pct(b.improvement) })
          : t("The model must be at least 5% more accurate AND not worse in percentage error before its forecast is shown.")}
      </p>
    </div>
  );
}

function SeasonView({ season, minimum, dataTo }: { season: Season; minimum: number; dataTo: string | null }) {
  const { t, tf } = useLanguage();
  const reason = season.reason ? tf(REASONS[season.reason] ? t(REASONS[season.reason]) : "", { minimum }) : "";
  const forecast = season.status === "forecast";
  const top = season.rows.slice(0, 10).map((r) => ({ name: r.product.length > 22 ? `${r.product.slice(0, 21)}…` : r.product, lastYear: r.lastYear, forecast: r.forecast ?? undefined }));
  return (
    <div className="space-y-5">
      <Card>
        <CardContent className="space-y-3 pt-5 text-sm">
          <p className="text-ink-2">
            {season.window
              ? tf("{season} {year}: {start} to {end}.", { season: season.name, year: season.targetYear ?? "", start: formatDate(season.window.start), end: formatDate(season.window.end) })
              : season.name}
            {dataTo ? ` ${tf("Your sales data runs to {date}.", { date: formatDate(dataTo) })}` : ""}
          </p>
          {forecast ? (
            <p role="status" className="flex items-start gap-2 text-success">
              <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{t("Forecast shown: the model beat last year's sales in past tests.")}</span>
            </p>
          ) : (
            <div role="status" className="space-y-1 rounded-xl border border-line bg-surface-2 px-4 py-3">
              <p className="flex items-center gap-2 font-medium text-ink">
                <Info className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                {season.status === "last_year_only" ? t("Last year's sales (no reliable forecast)") : t("Not enough data yet")}
              </p>
              <p className="text-ink-2">
                {reason}
                {season.reason === "too_early" && season.forecastDate ? ` ${tf("It can be made from {date}.", { date: formatDate(season.forecastDate) })}` : ""}
              </p>
            </div>
          )}
          <BackTestScores season={season} />
        </CardContent>
      </Card>

      {season.rows.length > 0 ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{forecast ? t("Top 10 products: last year and forecast") : t("Top 10 products: last year's sales")}</CardTitle>
              <CardDescription>{t("Units sold in the season window.")}</CardDescription>
            </CardHeader>
            <CardContent>
              <div role="img" aria-label={t("Bar chart of the ten best-selling products")} className="h-80 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={top} layout="vertical" margin={{ left: 8, right: 16 }}>
                    <CartesianGrid stroke={GRID} horizontal={false} />
                    <XAxis type="number" tick={AXIS_TICK} />
                    <YAxis type="category" dataKey="name" width={140} tick={AXIS_TICK} />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: 12, color: "#cbd5e1" }} />
                    <Bar dataKey="lastYear" name={t("Last year")} fill={SERIES_2} />
                    {forecast ? <Bar dataKey="forecast" name={t("Forecast")} fill={SERIES_1} /> : null}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("Products")}</CardTitle>
              {forecast ? <CardDescription>{t("Ranges are estimates: they cover the middle 80% of the model's past errors.")}</CardDescription> : null}
            </CardHeader>
            <CardContent>
              <ul className="space-y-3 md:hidden">
                {season.rows.map((r) => (
                  <li key={r.product} className="rounded-xl border border-line bg-surface-2 p-3 text-sm">
                    <p className="font-medium text-ink">{r.product}</p>
                    <p className="text-ink-2">{t("Last year")}: {formatNumber(r.lastYear)}</p>
                    {forecast ? <p className="text-ink-2">{t("Forecast")}: {forecastText(r)} <AdviceLabel advice={r.advice} /></p> : null}
                  </li>
                ))}
              </ul>
              <div className="hidden md:block">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">{t("Products")}</caption>
                  <thead className="text-xs text-muted">
                    <tr className="border-b border-line">
                      <th scope="col" className="py-2 pr-3 font-medium">{t("Product")}</th>
                      <th scope="col" className="py-2 pr-3 text-right font-medium">{t("Last year")}</th>
                      {forecast ? (
                        <>
                          <th scope="col" className="py-2 pr-3 text-right font-medium">{t("Forecast (estimate)")}</th>
                          <th scope="col" className="py-2 font-medium">{t("Advice")}</th>
                        </>
                      ) : null}
                    </tr>
                  </thead>
                  <tbody>
                    {season.rows.map((r) => (
                      <tr key={r.product} className="border-b border-line/60">
                        <td className="py-2.5 pr-3 font-medium text-ink">{r.product}</td>
                        <td className="py-2.5 pr-3 text-right tabular-nums">{formatNumber(r.lastYear)}</td>
                        {forecast ? (
                          <>
                            <td className="py-2.5 pr-3 text-right tabular-nums">{forecastText(r)}</td>
                            <td className="py-2.5"><AdviceLabel advice={r.advice} /></td>
                          </>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function forecastText(r: Season["rows"][number]) {
  if (r.forecast === null) return "-";
  return r.low !== null && r.high !== null ? `${formatNumber(r.forecast)} (${formatNumber(r.low)} - ${formatNumber(r.high)})` : formatNumber(r.forecast);
}
