"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Download, Search, SearchX } from "lucide-react";
import { CustomersTable } from "@/components/customers-table";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input, Select } from "@/components/ui/input";
import { downloadCsv } from "@/lib/csv-export";
import type { Customer, RiskLevel, SegmentName } from "@/lib/types";

const segments: SegmentName[] = [
  "Champions",
  "Loyal Customers",
  "Potential Loyalists",
  "At-Risk Customers",
  "Lost Customers",
];

const riskLevels: RiskLevel[] = ["Low", "Medium", "High", "Critical"];

type RiskFilter = RiskLevel | "all";

export function CustomerExplorer({
  customers,
  caption,
  initialRisk = "all",
  riskLabel = "Churn risk",
}: {
  customers: Customer[];
  caption: string;
  initialRisk?: RiskFilter;
  /** "Inactivity" for live data, where risk is rule-based. */
  riskLabel?: string;
}) {
  const [query, setQuery] = useState("");
  const [segment, setSegment] = useState<SegmentName | "all">("all");
  const [risk, setRisk] = useState<RiskFilter>(initialRisk);

  // Remember the filters and scroll position, so Back from a customer page returns to the same place.
  const storageKey = `customeriq:explorer:${usePathname()}`;
  const restored = useRef(false);

  useEffect(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) ?? "null");
      if (saved) {
        // Reading sessionStorage must wait until after hydration, so it is applied here.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setQuery(typeof saved.query === "string" ? saved.query : "");
        if (saved.segment === "all" || segments.includes(saved.segment)) setSegment(saved.segment);
        if (saved.risk === "all" || riskLevels.includes(saved.risk)) setRisk(saved.risk);
      }
      restored.current = true;
      const y = Number(saved?.scrollY) || 0;
      if (y > 0) {
        // The page above the table can still be growing (charts), so retry for a moment.
        let tries = 0;
        const timer = window.setInterval(() => {
          window.scrollTo(0, y);
          if (Math.abs(window.scrollY - y) < 4 || ++tries > 60) window.clearInterval(timer);
        }, 100);
        return () => window.clearInterval(timer);
      }
    } catch {
      restored.current = true;
    }
  }, [storageKey]);

  useEffect(() => {
    if (!restored.current) return;
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) ?? "null") ?? {};
      sessionStorage.setItem(storageKey, JSON.stringify({ ...saved, query, segment, risk }));
    } catch {}
  }, [storageKey, query, segment, risk]);

  function rememberScroll() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) ?? "null") ?? {};
      sessionStorage.setItem(storageKey, JSON.stringify({ ...saved, query, segment, risk, scrollY: window.scrollY }));
    } catch {}
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return customers.filter(
      (c) =>
        (segment === "all" || c.segment === segment) &&
        (risk === "all" || c.riskLevel === risk) &&
        (!q ||
          c.name.toLowerCase().includes(q) ||
          (c.email ?? "").toLowerCase().includes(q) ||
          c.id.toLowerCase().includes(q)),
    );
  }, [customers, query, segment, risk]);

  const riskOptions = [
    { value: "all" as const, label: `All (${riskLabel.toLowerCase()})`, count: customers.length },
    ...riskLevels.map((level) => ({
      value: level,
      label: level,
      count: customers.filter((c) => c.riskLevel === level).length,
    })),
  ];

  function exportCsv() {
    downloadCsv(
      `customeriq-customers-${new Date().toISOString().slice(0, 10)}.csv`,
      [
        "customer_id", "name", "email", "channel", "segment", riskLabel, "churn_probability_percent",
        "orders", "revenue", "clv_to_date", "last_purchase",
        "days_since_last_order", "recommended_action",
      ],
      filtered.map((c) => [
        c.id, c.name, c.email ?? "", c.channel, c.segment, c.riskLevel, c.churnProbability?.toFixed(1),
        c.orders, c.revenue, c.currentClv, c.lastPurchase,
        c.daysSinceLastOrder, c.recommendedAction,
      ]),
    );
  }

  function reset() {
    setQuery("");
    setSegment("all");
    setRisk("all");
  }

  return (
    <div className="space-y-4" onClickCapture={rememberScroll}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative sm:w-64">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint"
              aria-hidden="true"
            />
            <Input
              type="search"
              aria-label="Search customers"
              placeholder="Search name, email, or ID"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="pl-9"
            />
          </div>
          <Select
            aria-label="Filter by segment"
            value={segment}
            onChange={(event) => setSegment(event.target.value as SegmentName | "all")}
          >
            <option value="all">All segments</option>
            {segments.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
        <FilterPills label={`Filter by ${riskLabel.toLowerCase()}`} options={riskOptions} value={risk} onChange={setRisk} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted" aria-live="polite">
          Showing {filtered.length} of {customers.length} customers
        </p>
        <Button
          variant="secondary"
          onClick={exportCsv}
          disabled={filtered.length === 0}
          title="Downloads the customers shown above. Amounts are as imported (no currency conversion)."
        >
          <Download className="h-4 w-4" aria-hidden="true" />
          Download CSV
        </Button>
      </div>
      {filtered.length > 0 ? (
        <CustomersTable rows={filtered} caption={caption} riskLabel={riskLabel} />
      ) : (
        <EmptyState
          icon={SearchX}
          title="No customers match these filters"
          description={`Try a different search term, segment, or ${riskLabel.toLowerCase()} level.`}
          action={
            <Button variant="secondary" onClick={reset}>
              Clear filters
            </Button>
          }
        />
      )}
    </div>
  );
}