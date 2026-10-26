"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CircleCheck, HandCoins, TriangleAlert, Clock, FlaskConical, PackageSearch, Truck, Undo2 } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Skeleton } from "@/components/ui/skeleton";
import {
  SCORECARD_AVAILABLE,
  getScorecard,
  type CourierStats,
  type Scorecard,
  type ScorecardQuery,
} from "@/lib/api/couriers";
import { formatNumber, formatPercent } from "@/lib/utils";
import { fmt } from "@/lib/format";

const PERIODS: { value: string; days: number | null; label: string }[] = [
  { value: "30", days: 30, label: "Last 30 days" },
  { value: "90", days: 90, label: "Last 90 days" },
  { value: "365", days: 365, label: "Last year" },
  { value: "all", days: null, label: "All time" },
];

const selectClass =
  "w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40";

/**
 * The Courier Scorecard. A rate is shown only for a group with enough finished parcels (the backend decides
 * and sends `enough`); a smaller group shows its counts and "Not enough data yet", never a percentage.
 */
export function CourierScorecardBoard() {
  const [source, setSource] = useState("auto");
  const [period, setPeriod] = useState("all");
  const [city, setCity] = useState("");
  const [courier, setCourier] = useState("");
  const [card, setCard] = useState<Scorecard | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!SCORECARD_AVAILABLE) return;
    let cancelled = false;
    const query: ScorecardQuery = { source, days: PERIODS.find((p) => p.value === period)?.days ?? null, city, courier };
    getScorecard(query)
      .then((data) => !cancelled && (setCard(data), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [source, period, city, courier]);

  if (!SCORECARD_AVAILABLE) {
    return (
      <EmptyState
        icon={Truck}
        title="The scorecard needs your own shipments"
        description="There is no sample data for this page, because made-up courier numbers would be misleading. Connect the backend and import your shipments to see it."
      />
    );
  }
  if (failed) return <ErrorState title="Could not load the scorecard" description="Please check your connection and reload the page." />;
  if (!card) return <Skeleton className="h-64 w-full" />;

  if (card.realShipments + card.demoShipments === 0) {
    return (
      <EmptyState
        icon={PackageSearch}
        title="No shipments yet"
        description="Import your courier sheet and the scorecard will fill in."
        action={
          <Link href="/import" className="text-sm font-medium text-accent underline underline-offset-2">
            Go to Import Data
          </Link>
        }
      />
    );
  }

  const showingDemo = card.sourceUsed === "demo";
  const both = card.realShipments > 0 && card.demoShipments > 0;
  const stat = (n: number) => formatNumber(n);

  return (
    <div className="space-y-5">
      {showingDemo ? (
        <div role="status" className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-ink">
          <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
          <p>
            <strong>Demo data (synthetic).</strong>{" "}
            These shipments are made up to show how the page works. They are not real courier results.
          </p>
        </div>
      ) : null}

      <Card>
        <CardContent className="grid gap-4 pt-5 sm:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-2 sm:col-span-2 lg:col-span-3">
            <FilterPills
              label="Filter by period"
              value={period}
              onChange={setPeriod}
              options={PERIODS.map((p) => ({ value: p.value, label: p.label }))}
            />
            {both ? (
              <FilterPills
                label="Filter by data source"
                value={source}
                onChange={setSource}
                options={[
                  { value: "auto", label: "Real shipments", count: card.realShipments },
                  { value: "demo", label: "Demo (synthetic)", count: card.demoShipments },
                  { value: "all", label: "Both together" },
                ]}
              />
            ) : null}
          </div>
          <label className="space-y-1 text-xs font-medium text-muted">
            City
            <select className={selectClass} value={city} onChange={(e) => setCity(e.target.value)}>
              <option value="">All cities</option>
              {card.allCities.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-xs font-medium text-muted">
            Courier name
            <select className={selectClass} value={courier} onChange={(e) => setCourier(e.target.value)}>
              <option value="">All couriers</option>
              {card.allCouriers.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <p className="self-end text-xs text-muted">
            {fmt("{count} shipments shown. A rate needs at least {minimum} finished parcels (delivered or returned).", {
              count: stat(card.shipments),
              minimum: card.minGroupCount,
            })}
          </p>
        </CardContent>
      </Card>

      {card.alerts.length > 0 ? (
        <section aria-label="Unusual returns" className="space-y-3">
          {card.alerts.map((a) => (
            <div key={`${a.courier}|${a.city}`} role="note" className="flex items-start gap-3 rounded-xl border border-serious/40 bg-serious/10 px-4 py-3 text-sm text-ink">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-serious" aria-hidden="true" />
              <div className="space-y-1">
                <p className="font-medium">Unusual returns</p>
                <p>
                  {fmt("{courier}'s return rate in {city} is {rate} vs {others} for other couriers (based on {closed} and {othersClosed} parcels).", {
                    courier: a.courier, city: a.city, rate: formatPercent(a.rate * 100, 0), others: formatPercent(a.othersRate * 100, 0),
                    closed: a.closed, othersClosed: a.othersClosed,
                  })}
                </p>
                <p className="text-xs text-ink-2">High returns may also come from customers or products; check before deciding.</p>
              </div>
            </div>
          ))}
        </section>
      ) : null}

      {card.rows.length === 0 ? (
        <EmptyState icon={PackageSearch} title="No shipments match these filters" description="Try a longer period or another city." />
      ) : (
        <>
          <section aria-label="Courier totals" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {card.couriers.map((c) => (
              <CourierCard key={c.courier} stats={c} />
            ))}
          </section>

          <Card>
            <CardHeader>
              <CardTitle>Each courier in each city</CardTitle>
            </CardHeader>
            <CardContent>
              {/* Phone: one card per row, so nothing scrolls sideways. */}
              <ul className="space-y-3 md:hidden">
                {card.rows.map((r) => (
                  <li key={`${r.courier}|${r.city}`} className="rounded-xl border border-line bg-surface-2 p-3">
                    <p className="font-medium text-ink">
                      {r.courier} <span className="text-muted">· {r.city ?? "No city"}</span>
                    </p>
                    <Figures stats={r} />
                  </li>
                ))}
              </ul>
              <div className="hidden md:block">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Each courier in each city</caption>
                  <thead className="text-xs text-muted">
                    <tr className="border-b border-line">
                      <th scope="col" className="py-2 pr-3 font-medium">Courier name</th>
                      <th scope="col" className="py-2 pr-3 font-medium">City</th>
                      <th scope="col" className="py-2 pr-3 text-right font-medium">Shipments</th>
                      <th scope="col" className="py-2 pr-3 font-medium">Delivered</th>
                      <th scope="col" className="py-2 pr-3 font-medium">Returned</th>
                      <th scope="col" className="py-2 pr-3 font-medium">Average days to deliver</th>
                      <th scope="col" className="py-2 pr-3 font-medium">Average days to pay</th>
                      <th scope="col" className="py-2 text-right font-medium">Refused</th>
                    </tr>
                  </thead>
                  <tbody>
                    {card.rows.map((r) => (
                      <tr key={`${r.courier}|${r.city}`} className="border-b border-line/60 align-top">
                        <td className="py-2.5 pr-3 font-medium text-ink">{r.courier}</td>
                        <td className="py-2.5 pr-3 text-ink-2">{r.city ?? "No city"}</td>
                        <td className="py-2.5 pr-3 text-right tabular-nums">{stat(r.shipments)}</td>
                        {r.enough ? (
                          <>
                            <td className="py-2.5 pr-3 tabular-nums"><Rate icon={CircleCheck} value={r.deliveryRate} /></td>
                            <td className="py-2.5 pr-3 tabular-nums"><Rate icon={Undo2} value={r.returnRate} /></td>
                            <td className="py-2.5 pr-3 tabular-nums">
                              {r.averageDays === null ? "-" : fmt("{days} days", { days: r.averageDays })}
                            </td>
                          </>
                        ) : (
                          <td colSpan={3} className="py-2.5 pr-3 text-muted">
                            <NotEnough stats={r} />
                          </td>
                        )}
                        <td className="py-2.5 pr-3 tabular-nums">
                          {r.averageDaysToPay !== null ? fmt("{days} days", { days: r.averageDaysToPay }) : <span className="text-muted">{r.paidParcels > 0 || r.enough ? "Not enough data yet" : "-"}</span>}
                        </td>
                        <td className="py-2.5 text-right tabular-nums">{stat(r.refused)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function Rate({ icon: Icon, value }: { icon: typeof Clock; value: number | null }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
      {value === null ? "-" : formatPercent(value * 100, 0)}
    </span>
  );
}

function NotEnough({ stats }: { stats: CourierStats }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2">
      <Clock className="h-3.5 w-3.5" aria-hidden="true" />
      <span>Not enough data yet</span>
      <span className="text-xs">
        {fmt("({finished} finished, {needed} more needed)", { finished: stats.closed, needed: stats.needed })}
      </span>
    </span>
  );
}

/** The same figures as a table row, for the phone cards and the courier summaries. */
function Figures({ stats }: { stats: CourierStats }) {
  return (
    <div className="mt-2 space-y-1 text-sm text-ink-2">
      <p>
        {fmt("{count} shipments", { count: formatNumber(stats.shipments) })}
        {stats.refused > 0 ? ` · ${fmt("{count} refused", { count: stats.refused })}` : ""}
      </p>
      {stats.enough ? (
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          <li className="inline-flex items-center gap-1.5"><CircleCheck className="h-3.5 w-3.5 text-muted" aria-hidden="true" />Delivered {stats.deliveryRate === null ? "-" : formatPercent(stats.deliveryRate * 100, 0)}</li>
          <li className="inline-flex items-center gap-1.5"><Undo2 className="h-3.5 w-3.5 text-muted" aria-hidden="true" />Returned {stats.returnRate === null ? "-" : formatPercent(stats.returnRate * 100, 0)}</li>
          {stats.averageDays !== null ? (
            <li className="inline-flex items-center gap-1.5"><Clock className="h-3.5 w-3.5 text-muted" aria-hidden="true" />{fmt("{days} days", { days: stats.averageDays })}</li>
          ) : null}
          {stats.averageDaysToPay !== null ? (
            <li className="inline-flex items-center gap-1.5"><HandCoins className="h-3.5 w-3.5 text-muted" aria-hidden="true" />Average days to pay {fmt("{days} days", { days: stats.averageDaysToPay })}</li>
          ) : null}
        </ul>
      ) : (
        <p className="text-muted"><NotEnough stats={stats} /></p>
      )}
    </div>
  );
}

function CourierCard({ stats }: { stats: CourierStats }) {
  const extra: string[] = [];
  if (stats.inTransit > 0) extra.push(fmt("{count} on the way", { count: stats.inTransit }));
  if (stats.lost > 0) extra.push(fmt("{count} lost", { count: stats.lost }));
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Truck className="h-4 w-4 text-accent" aria-hidden="true" />
          {stats.courier}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Figures stats={stats} />
        {extra.length > 0 ? <p className="mt-1 text-xs text-muted">{extra.join(" · ")}</p> : null}
      </CardContent>
    </Card>
  );
}
