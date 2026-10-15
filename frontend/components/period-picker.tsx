"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FilterPills } from "@/components/ui/filter-pills";

export const PERIOD_OPTIONS = [30, 90, 180, 365] as const;
export const DEFAULT_PERIOD = 90;

/** Chooses how many days the revenue and retention figures cover (kept in the page address). */
export function PeriodPicker({ current }: { current: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  function choose(days: string) {
    const next = new URLSearchParams(params.toString());
    if (Number(days) === DEFAULT_PERIOD) next.delete("days");
    else next.set("days", days);
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-xs font-medium text-slate-500">Period for revenue, retention and growth:</span>
      <FilterPills
        label="Period"
        value={String(current)}
        onChange={choose}
        options={PERIOD_OPTIONS.map((days) => ({ value: String(days), label: `Last ${days} days` }))}
      />
    </div>
  );
}
