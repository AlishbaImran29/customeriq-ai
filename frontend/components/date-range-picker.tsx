"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  MAX_RANGE_DAYS,
  dayCount,
  formatRange,
  lastDays,
  monthNames,
  monthWeeks,
  presets,
  previousRange,
  viewOf,
  type DateRange,
} from "@/lib/dates";
import { cn } from "@/lib/utils";

const DEFAULT_DAYS = 90;
const WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const MONTHS = monthNames();
const YEARS_BACK = 15;
const selectClass =
  "rounded-lg border border-line bg-surface-2 px-2 py-1 text-sm font-semibold text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40";

/**
 * Calendar for choosing the period behind the revenue, retention and growth figures.
 * Quick choices and "today" are counted from the last day of data (`asOf`), because
 * imported files are often not from this week. The choice lives in the page address.
 */
export function DateRangePicker({ asOf, current }: { asOf: string; current: DateRange }) {
  const router = useRouter();
  const pathname = usePathname();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<{ from: string; to: string | null }>(current);
  const [view, setView] = useState(() => viewOf(current.to));

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onClick = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  function openPanel() {
    setDraft(current);
    setView(viewOf(current.to));
    setOpen(true);
  }

  function pick(day: string) {
    // A first click starts a range; the second finishes it (in either order).
    if (!draft.from || draft.to) setDraft({ from: day, to: null });
    else setDraft(day < draft.from ? { from: day, to: draft.from } : { from: draft.from, to: day });
  }

  function shiftMonth(delta: number) {
    setView((v) => {
      const index = v.year * 12 + v.month + delta;
      return { year: Math.floor(index / 12), month: ((index % 12) + 12) % 12 };
    });
  }

  const last = viewOf(asOf); // the calendar cannot go past the month of the last data day
  const atLastMonth = view.year * 12 + view.month >= last.year * 12 + last.month;
  const years = Array.from({ length: YEARS_BACK + 1 }, (_, i) => last.year - i);
  if (!years.includes(view.year)) years.push(view.year);
  years.sort((a, b) => b - a);

  const complete = draft.to !== null ? ({ from: draft.from, to: draft.to } satisfies DateRange) : null;
  const tooLong = complete ? dayCount(complete) > MAX_RANGE_DAYS : false;
  const days = complete ? dayCount(complete) : 0;

  function apply() {
    if (!complete || tooLong) return;
    const normal = lastDays(asOf, DEFAULT_DAYS);
    const isDefault = complete.from === normal.from && complete.to === normal.to;
    router.replace(isDefault ? pathname : `${pathname}?from=${complete.from}&to=${complete.to}`, { scroll: false });
    setOpen(false);
  }

  const inDraft = (day: string) => {
    const end = draft.to ?? draft.from;
    return day >= draft.from && day <= end;
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => (open ? setOpen(false) : openPanel())}
        aria-expanded={open}
        aria-haspopup="dialog"
        className="inline-flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-sm font-medium text-ink shadow-sm hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
      >
        <CalendarDays className="h-4 w-4 text-accent" aria-hidden="true" />
        {formatRange(current)}
        <span className="text-xs font-normal text-muted">({dayCount(current)} days)</span>
      </button>

      {open ? (
        <div
          role="dialog"
          aria-label="Choose a period"
          className="absolute left-0 z-30 mt-2 flex w-[min(94vw,560px)] flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-xl sm:flex-row"
        >
          <div className="flex flex-wrap gap-1.5 sm:w-40 sm:shrink-0 sm:flex-col">
            {presets(asOf).map((preset) => {
              const active = draft.to !== null && preset.range.from === draft.from && preset.range.to === draft.to;
              return (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => {
                    setDraft(preset.range);
                    setView(viewOf(preset.range.to));
                  }}
                  aria-pressed={active}
                  className={cn(
                    "rounded-lg px-2.5 py-1.5 text-left text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40",
                    active ? "bg-accent text-accent-ink" : "bg-surface-2 text-ink-2 hover:bg-accent/10 hover:text-accent",
                  )}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>

          <div className="min-w-0 flex-1">
            <div className="mb-2 flex items-center justify-between">
              <button
                type="button"
                onClick={() => shiftMonth(-1)}
                aria-label="Previous month"
                className="rounded-lg p-1.5 text-ink-2 hover:bg-surface-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
              >
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              </button>
              <div className="flex items-center gap-1.5">
                <select
                  aria-label="Month"
                  value={view.month}
                  onChange={(event) => setView((v) => ({ ...v, month: Number(event.target.value) }))}
                  className={selectClass}
                >
                  {MONTHS.map((name, month) => (
                    <option key={name} value={month} disabled={view.year === last.year && month > last.month}>
                      {name}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Year"
                  value={view.year}
                  onChange={(event) => {
                    const year = Number(event.target.value);
                    // Keep the month, but never land after the last month of data.
                    setView((v) => ({ year, month: year === last.year ? Math.min(v.month, last.month) : v.month }));
                  }}
                  className={selectClass}
                >
                  {years.map((year) => (
                    <option key={year} value={year}>
                      {year}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={() => shiftMonth(1)}
                disabled={atLastMonth}
                aria-label="Next month"
                className="rounded-lg p-1.5 text-ink-2 hover:bg-surface-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-30"
              >
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="grid grid-cols-7 text-center text-[11px] font-medium text-faint">
              {WEEKDAYS.map((day) => (
                <span key={day} className="py-1">
                  {day}
                </span>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-y-0.5">
              {monthWeeks(view.year, view.month)
                .flat()
                .map((day, index) => {
                  if (day === null) return <span key={`blank-${index}`} />;
                  const disabled = day > asOf;
                  const selected = day === draft.from || day === draft.to;
                  return (
                    <button
                      key={day}
                      type="button"
                      disabled={disabled}
                      onClick={() => pick(day)}
                      aria-label={formatRange({ from: day, to: day })}
                      aria-pressed={selected}
                      className={cn(
                        "h-8 text-xs tabular-nums transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40",
                        disabled && "cursor-not-allowed text-faint",
                        !disabled && !selected && inDraft(day) && "bg-accent/20 text-accent",
                        !disabled && !selected && !inDraft(day) && "text-ink-2 hover:bg-surface-3",
                        selected && "rounded-md bg-accent font-semibold text-accent-ink",
                      )}
                    >
                      {Number(day.slice(8))}
                    </button>
                  );
                })}
            </div>
            <p className="mt-2 text-[11px] text-faint">Days after {formatRange({ from: asOf, to: asOf })} (the last day of data) are not selectable.</p>

            <div className="mt-3 flex flex-col gap-3 border-t border-line/60 pt-3">
              <div className="text-xs text-ink-2">
                {complete ? (
                  <>
                    <p className="font-medium text-ink">{formatRange(complete)}</p>
                    <p>{days} days</p>
                    {tooLong ? (
                      <p className="mt-1 text-danger">Choose at most {MAX_RANGE_DAYS} days (about 3 years).</p>
                    ) : (
                      <p className="mt-1 text-muted">Compared with the {days} days before: {formatRange(previousRange(complete))}.</p>
                    )}
                  </>
                ) : (
                  <p>Click an end date to finish the range.</p>
                )}
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => setOpen(false)} className="flex-1">
                  Cancel
                </Button>
                <Button onClick={apply} disabled={!complete || tooLong} className="flex-1">
                  Apply
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
