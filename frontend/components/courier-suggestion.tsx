"use client";

import { useEffect, useState } from "react";
import { Lightbulb } from "lucide-react";
import { SCORECARD_AVAILABLE, getCourierSuggestion, type CourierSuggestion } from "@/lib/api/couriers";
import { formatPercent } from "@/lib/utils";
import { fmt } from "@/lib/format";

/**
 * Under the courier box of Add Order: which courier has returned the fewest parcels in this city, but only
 * when the city's history is long enough (the backend applies the minimum). Otherwise it says there is not
 * enough history. It is advice from past parcels, never a promise.
 */
export function CourierSuggestionNote({ city, onPick }: { city: string; onPick: (courier: string) => void }) {
  const [found, setFound] = useState<{ city: string; value: CourierSuggestion | null } | null>(null);

  useEffect(() => {
    const typed = city.trim();
    if (!SCORECARD_AVAILABLE || typed.length < 3) return;
    let cancelled = false;
    // Wait for a pause in typing so the server is not asked after every letter.
    const timer = setTimeout(() => {
      getCourierSuggestion(typed)
        .then((value) => !cancelled && setFound({ city: typed, value }))
        .catch(() => !cancelled && setFound(null));
    }, 500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [city]);

  const typed = city.trim();
  if (!SCORECARD_AVAILABLE || typed.length < 3 || !found || found.city !== typed || !found.value) return null;
  const { value } = found;
  return (
    <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted" role="note">
      <Lightbulb className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {value.available && value.best ? (
        <>
          <span>
            {fmt("Fewest returns in {city}: {courier} ({rate} returned, {closed} parcels).", {
              city: value.city, courier: value.best.courier, rate: formatPercent((value.best.returnRate ?? 0) * 100, 0), closed: value.best.closed,
            })}
            {value.sourceUsed === "demo" ? ` ${"(demo data)"}` : ""}
          </span>
          <button
            type="button"
            onClick={() => onPick(value.best!.courier)}
            className="rounded font-medium text-accent underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
          >
            {fmt("Use {courier}", { courier: value.best.courier })}
          </button>
        </>
      ) : (
        <span>No courier has enough history in this city yet.</span>
      )}
    </p>
  );
}
