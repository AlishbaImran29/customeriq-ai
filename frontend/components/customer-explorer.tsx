"use client";

import { useMemo, useState } from "react";
import { Search, SearchX } from "lucide-react";
import { CustomersTable } from "@/components/customers-table";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input, Select } from "@/components/ui/input";
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
}: {
  customers: Customer[];
  caption: string;
  initialRisk?: RiskFilter;
}) {
  const [query, setQuery] = useState("");
  const [segment, setSegment] = useState<SegmentName | "all">("all");
  const [risk, setRisk] = useState<RiskFilter>(initialRisk);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return customers.filter(
      (c) =>
        (segment === "all" || c.segment === segment) &&
        (risk === "all" || c.riskLevel === risk) &&
        (!q ||
          c.name.toLowerCase().includes(q) ||
          c.email.toLowerCase().includes(q) ||
          c.id.toLowerCase().includes(q)),
    );
  }, [customers, query, segment, risk]);

  const riskOptions = [
    { value: "all" as const, label: "All risk", count: customers.length },
    ...riskLevels.map((level) => ({
      value: level,
      label: level,
      count: customers.filter((c) => c.riskLevel === level).length,
    })),
  ];

  function reset() {
    setQuery("");
    setSegment("all");
    setRisk("all");
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative sm:w-64">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
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
        <FilterPills label="Filter by churn risk" options={riskOptions} value={risk} onChange={setRisk} />
      </div>
      <p className="text-xs text-slate-500" aria-live="polite">
        Showing {filtered.length} of {customers.length} customers
      </p>
      {filtered.length > 0 ? (
        <CustomersTable rows={filtered} caption={caption} />
      ) : (
        <EmptyState
          icon={SearchX}
          title="No customers match these filters"
          description="Try a different search term, segment, or risk level."
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