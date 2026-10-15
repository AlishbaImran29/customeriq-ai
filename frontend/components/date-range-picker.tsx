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
  monthTitle,
  monthWeeks,
  presets,
  previousRange,
  viewOf,
  type DateRange,
} from "@/lib/dates";
import { cn } from "@/lib/utils";

const DEFAULT_DAYS = 90;
const WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

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
        className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
      >
        <CalendarDays className="h-4 w-4 text-teal-700" aria-hidden="true" />
        {formatRange(current)}
        <span className="text-xs font-normal text-slate-500">({dayCount(current)} days)</span>
      </button>

      {open ? (
        <div
          role="dialog"
          aria-label="Choose a period"
          className="absolute left-0 z-30 mt-2 flex w-[min(94vw,600px)] flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-xl sm:flex-row"
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
                    "rounded-lg px-2.5 py-1.5 text-left text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40",
                    active ? "bg-teal-600 text-white" : "bg-slate-50 text-slate-700 hover:bg-teal-50 hover:text-teal-800",
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
                className="rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
              >
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              </button>
              <p className="text-sm font-semibold text-slate-900" aria-live="polite">
                {monthTitle(view.year, view.month)}
              </p>
              <button
                type="button"
                onClick={() => shiftMonth(1)}
                aria-label="Next month"
                className="rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
              >
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="grid grid-cols-7 text-center text-[11px] font-medium text-slate-400">
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
                        "h-8 text-xs tabular-nums transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40",
                        disabled && "cursor-not-allowed text-slate-300",
                        !disabled && !selected && inDraft(day) && "bg-teal-100 text-teal-900",
                        !disabled && !selected && !inDraft(day) && "text-slate-700 hover:bg-slate-100",
                        selected && "rounded-md bg-teal-600 font-semibold text-white",
                      )}
                    >
                      {Number(day.slice(8))}
                    </button>
                  );
                })}
            </div>
            <p className="mt-2 text-[11px] text-slate-400">Days after {formatRange({ from: asOf, to: asOf })} (the last day of data) are not selectable.</p>
          </div>

          <div className="flex flex-col justify-between gap-3 sm:w-48 sm:shrink-0">
            <div className="text-xs text-slate-600">
              {complete ? (
                <>
                  <p className="font-medium text-slate-900">{formatRange(complete)}</p>
                  <p>{days} days</p>
                  {tooLong ? (
                    <p className="mt-1 text-rose-700">Choose at most {MAX_RANGE_DAYS} days (about 3 years).</p>
                  ) : (
                    <p className="mt-1 text-slate-500">Compared with the {days} days before: {formatRange(previousRange(complete))}.</p>
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
      ) : null}
    </div>
  );
}
