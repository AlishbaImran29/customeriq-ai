"use client";

import { useState } from "react";
import { ArrowRight, Lightbulb, Target, Users } from "lucide-react";
import { EmptyState } from "@/components/states";
import { Badge, impactVariant } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import type { Recommendation, RecommendationCategory } from "@/lib/types";
import { formatCompactCurrency, formatNumber } from "@/lib/utils";

const categories: RecommendationCategory[] = [
  "Retention Campaign",
  "Upsell",
  "Cross-Sell",
  "Customer Recovery",
];

type Filter = RecommendationCategory | "all";

export function RecommendationBoard({ items }: { items: Recommendation[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const visible = filter === "all" ? items : items.filter((i) => i.category === filter);

  const options = [
    { value: "all" as const, label: "All", count: items.length },
    ...categories.map((c) => ({
      value: c,
      label: c,
      count: items.filter((i) => i.category === c).length,
    })),
  ];

  return (
    <div className="space-y-4">
      <FilterPills label="Filter by recommendation type" options={options} value={filter} onChange={setFilter} />
      {visible.length === 0 ? (
        <EmptyState
          icon={Lightbulb}
          title="No recommendations in this category"
          description="New recommendations appear here as customer behaviour changes."
        />
      ) : (
        <ul className="grid gap-4 lg:grid-cols-2">
          {visible.map((item) => (
            <li key={item.id}>
              <Card className="flex h-full flex-col">
                <CardContent className="flex flex-1 flex-col pt-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="brand">{item.category}</Badge>
                    <Badge variant={impactVariant(item.impact)}>{item.impact} impact</Badge>
                    <span className="ml-auto text-xs text-slate-400">{item.id}</span>
                  </div>
                  <h2 className="mt-3 text-base font-semibold text-slate-900">{item.title}</h2>
                  <p className="mt-2 text-sm text-slate-600">{item.detail}</p>
                  <dl className="mt-4 grid grid-cols-3 gap-3 text-xs">
                    <div>
                      <dt className="flex items-center gap-1 text-slate-500">
                        <Target className="h-3.5 w-3.5" aria-hidden="true" /> Segment
                      </dt>
                      <dd className="mt-0.5 font-medium text-slate-800">{item.targetSegment}</dd>
                    </div>
                    <div>
                      <dt className="flex items-center gap-1 text-slate-500">
                        <Users className="h-3.5 w-3.5" aria-hidden="true" /> Audience
                      </dt>
                      <dd className="mt-0.5 font-medium tabular-nums text-slate-800">
                        {formatNumber(item.audienceSize)}
                      </dd>
                    </div>
                    <div>
                      {item.estimatedRevenue !== null ? (
                        <>
                          <dt className="text-slate-500">Est. revenue</dt>
                          <dd className="mt-0.5 font-medium tabular-nums text-emerald-700">
                            +{formatCompactCurrency(item.estimatedRevenue)}
                          </dd>
                        </>
                      ) : (
                        <>
                          <dt className="text-slate-500" title="What this audience actually spent in the last 12 months. Not a forecast.">
                            Spent (12 mo)
                          </dt>
                          <dd className="mt-0.5 font-medium tabular-nums text-slate-800">
                            {formatCompactCurrency(item.historicalRevenue ?? 0)}
                          </dd>
                        </>
                      )}
                    </div>
                  </dl>
                  <div className="mt-auto pt-4">
                    <p className="flex items-start gap-2 rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700">
                      <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-teal-600" aria-hidden="true" />
                      <span>
                        <span className="font-medium">Next best action: </span>
                        {item.nextAction}
                      </span>
                    </p>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}