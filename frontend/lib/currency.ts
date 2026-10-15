"use client";

import { useEffect, useSyncExternalStore } from "react";

// Display currency. The stored numbers never change: they are in the currency of the
// imported file ("source"). Choosing another "target" multiplies by a real exchange
// rate fetched from a free public service. If the rate cannot be loaded, values stay
// in the source currency and are labelled that way (we never guess a rate).

export const CURRENCIES = [
  { code: "USD", name: "US dollar" },
  { code: "PKR", name: "Pakistani rupee" },
  { code: "GBP", name: "British pound" },
  { code: "EUR", name: "Euro" },
  { code: "INR", name: "Indian rupee" },
  { code: "AED", name: "UAE dirham" },
  { code: "SAR", name: "Saudi riyal" },
  { code: "CAD", name: "Canadian dollar" },
  { code: "AUD", name: "Australian dollar" },
] as const;

export type CurrencyCode = (typeof CURRENCIES)[number]["code"];

export type CurrencyState = {
  /** Currency the imported numbers are in. */
  source: CurrencyCode;
  /** Currency the user wants to see. */
  target: CurrencyCode;
  /** Multiplier source -> target; null when not converting or not yet known. */
  rate: number | null;
  /** When the rate was published by the service (UTC text), if known. */
  updated: string | null;
  status: "same" | "loading" | "ready" | "unavailable";
};

const DEFAULT_STATE: CurrencyState = { source: "USD", target: "USD", rate: null, updated: null, status: "same" };
const PREFS_KEY = "ciq_currency";
const RATE_KEY = "ciq_rate";
const RATE_MAX_AGE_MS = 12 * 60 * 60 * 1000;

let current: CurrencyState = DEFAULT_STATE;
let started = false;
const listeners = new Set<() => void>();

function set(next: CurrencyState) {
  current = next;
  listeners.forEach((listener) => listener());
}

function isCode(value: unknown): value is CurrencyCode {
  return CURRENCIES.some((c) => c.code === value);
}

function readJson(key: string): unknown {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Private mode or blocked storage: the choice just won't be remembered.
  }
}

type StoredRate = { source: string; target: string; rate: number; updated: string | null; savedAt: number };

async function loadRate(source: CurrencyCode, target: CurrencyCode) {
  const cached = readJson(RATE_KEY) as StoredRate | null;
  if (cached && cached.source === source && cached.target === target && Date.now() - cached.savedAt < RATE_MAX_AGE_MS) {
    return { rate: cached.rate, updated: cached.updated };
  }
  try {
    const response = await fetch(`https://open.er-api.com/v6/latest/${source}`);
    const data = (await response.json()) as { result?: string; rates?: Record<string, number>; time_last_update_utc?: string };
    const rate = data.rates?.[target];
    if (data.result !== "success" || typeof rate !== "number" || !(rate > 0)) return null;
    const updated = data.time_last_update_utc ?? null;
    writeJson(RATE_KEY, { source, target, rate, updated, savedAt: Date.now() } satisfies StoredRate);
    return { rate, updated };
  } catch {
    // Offline: an older saved rate for the same pair is better than none, and is labelled with its date.
    if (cached && cached.source === source && cached.target === target) return { rate: cached.rate, updated: cached.updated };
    return null;
  }
}

async function apply(source: CurrencyCode, target: CurrencyCode) {
  if (source === target) {
    set({ source, target, rate: null, updated: null, status: "same" });
    return;
  }
  set({ source, target, rate: null, updated: null, status: "loading" });
  const result = await loadRate(source, target);
  // Ignore the answer if the user picked something else while we waited.
  if (current.source !== source || current.target !== target) return;
  set(
    result
      ? { source, target, rate: result.rate, updated: result.updated, status: "ready" }
      : { source, target, rate: null, updated: null, status: "unavailable" },
  );
}

function start() {
  if (started) return;
  started = true;
  const stored = readJson(PREFS_KEY) as { source?: unknown; target?: unknown } | null;
  const source = isCode(stored?.source) ? stored.source : DEFAULT_STATE.source;
  const target = isCode(stored?.target) ? stored.target : source;
  void apply(source, target);
}

export function setCurrencies(source: CurrencyCode, target: CurrencyCode) {
  writeJson(PREFS_KEY, { source, target });
  void apply(source, target);
}

/** The currency the numbers are really shown in right now. */
function shownCurrency(state: CurrencyState): CurrencyCode {
  return state.status === "ready" ? state.target : state.source;
}

function convert(state: CurrencyState, value: number) {
  return state.status === "ready" && state.rate ? value * state.rate : value;
}

export function getCurrencyState() {
  return current;
}

export function formatMoney(state: CurrencyState, value: number, compact = false) {
  const amount = convert(state, value);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: shownCurrency(state),
    ...(compact
      ? { notation: "compact" as const, maximumFractionDigits: 1 }
      : { maximumFractionDigits: Math.abs(amount) >= 1000 ? 0 : 2 }),
  }).format(amount);
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Subscribes to the currency choice (server and first render use the default, so hydration matches). */
export function useCurrency() {
  const state = useSyncExternalStore(subscribe, () => current, () => DEFAULT_STATE);
  useEffect(start, []);
  return {
    state,
    format: (value: number) => formatMoney(state, value),
    formatCompact: (value: number) => formatMoney(state, value, true),
  };
}
