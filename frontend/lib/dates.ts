// Calendar-date helpers. Dates are plain "YYYY-MM-DD" strings handled in UTC, so the
// time zone of the browser or server can never shift a day.

export type DateRange = { from: string; to: string };

/** Longest period the backend accepts (about three years). */
export const MAX_RANGE_DAYS = 1095;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const DAY_MS = 86_400_000;

export function isIsoDate(value: unknown): value is string {
  if (typeof value !== "string" || !ISO_DATE.test(value)) return false;
  return toIso(parse(value)) === value; // rejects 2026-02-31 and similar
}

function parse(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

export function toIso(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function addDays(iso: string, days: number): string {
  return toIso(new Date(parse(iso).getTime() + days * DAY_MS));
}

/** Number of days in the range, counting both ends. */
export function dayCount(range: DateRange): number {
  return Math.round((parse(range.to).getTime() - parse(range.from).getTime()) / DAY_MS) + 1;
}

export function lastDays(asOf: string, days: number): DateRange {
  return { from: addDays(asOf, -(days - 1)), to: asOf };
}

function monthStart(year: number, month: number): string {
  return toIso(new Date(Date.UTC(year, month, 1)));
}

function monthEnd(year: number, month: number): string {
  return toIso(new Date(Date.UTC(year, month + 1, 0)));
}

/** Quick choices, counted back from the last day of data (not from today's date). */
export function presets(asOf: string): { label: string; range: DateRange }[] {
  const end = parse(asOf);
  const y = end.getUTCFullYear();
  const m = end.getUTCMonth();
  return [
    { label: "Last 7 days", range: lastDays(asOf, 7) },
    { label: "Last 30 days", range: lastDays(asOf, 30) },
    { label: "Last 90 days", range: lastDays(asOf, 90) },
    { label: "Last 6 months", range: lastDays(asOf, 182) },
    { label: "Last 12 months", range: lastDays(asOf, 365) },
    { label: "This month", range: { from: monthStart(y, m), to: asOf } },
    { label: "Last month", range: { from: monthStart(y, m - 1), to: monthEnd(y, m - 1) } },
    { label: "This year", range: { from: monthStart(y, 0), to: asOf } },
    { label: "Last year", range: { from: monthStart(y - 1, 0), to: monthEnd(y - 1, 11) } },
  ];
}

export function formatDay(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(parse(iso));
}

export function formatRange(range: DateRange): string {
  return range.from === range.to ? formatDay(range.from) : `${formatDay(range.from)} – ${formatDay(range.to)}`;
}

/** The equally long period right before `range`, used for the comparison. */
export function previousRange(range: DateRange): DateRange {
  const days = dayCount(range);
  return { from: addDays(range.from, -days), to: addDays(range.from, -1) };
}

export function monthTitle(year: number, month: number): string {
  return new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(year, month, 1)));
}

/** Weeks (Monday first) of a month; null pads the days that belong to the neighbouring months. */
export function monthWeeks(year: number, month: number): (string | null)[][] {
  const first = new Date(Date.UTC(year, month, 1));
  const lead = (first.getUTCDay() + 6) % 7; // Monday = 0
  const total = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const cells: (string | null)[] = Array(lead).fill(null);
  for (let day = 1; day <= total; day++) cells.push(toIso(new Date(Date.UTC(year, month, day))));
  while (cells.length % 7 !== 0) cells.push(null);
  const weeks: (string | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

/** Reads ?from=&to= from the page address; null unless both are real dates in order. */
export function rangeFromParams(from: unknown, to: unknown): DateRange | null {
  if (!isIsoDate(from) || !isIsoDate(to) || from > to) return null;
  return { from, to };
}

export function viewOf(iso: string): { year: number; month: number } {
  const d = parse(iso);
  return { year: d.getUTCFullYear(), month: d.getUTCMonth() };
}
