"use client";

import Link from "next/link";
import { useLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** The six steps of a launch. Only the ones that exist so far are links; the rest are marked "coming next". */
const STEPS = [
  { name: "Trend", href: "/launch/trends" },
  { name: "Vendors", href: null },
  { name: "Competitors", href: null },
  { name: "Creatives", href: null },
  { name: "Profit check", href: null },
  { name: "Launch", href: null },
] as const;

export function LaunchSteps({ current }: { current: number }) {
  const { t, tf } = useLanguage();
  const step = STEPS[current - 1];
  return (
    <nav aria-label={t("Launch steps")} className="space-y-2">
      <p className="text-sm font-medium text-ink">
        {tf("Step {n} of {total}: {name}", { n: current, total: STEPS.length, name: t(step.name) })}
      </p>
      <ol className="flex flex-wrap gap-2">
        {STEPS.map((s, i) => {
          const active = i + 1 === current;
          const body = (
            <>
              <span
                aria-hidden="true"
                className={cn("grid h-5 w-5 place-items-center rounded-full text-[11px] font-semibold", active ? "bg-accent text-accent-ink" : "bg-surface-3 text-muted")}
              >
                {i + 1}
              </span>
              {t(s.name)}
              {!s.href ? <span className="text-[10px] text-faint">({t("coming next")})</span> : null}
            </>
          );
          const base = "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium";
          return (
            <li key={s.name}>
              {s.href ? (
                <Link
                  href={s.href}
                  aria-current={active ? "step" : undefined}
                  className={cn(base, "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40", active ? "border-accent text-ink" : "border-line text-ink-2 hover:border-accent/40")}
                >
                  {body}
                </Link>
              ) : (
                <span className={cn(base, "border-line/60 text-faint")}>{body}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
