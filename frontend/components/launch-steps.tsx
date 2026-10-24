"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** The six steps of a launch, each with its own page. The chosen project travels in the address (?project=ID). */
const STEPS = [
  { name: "Trend", href: "/launch/trends" },
  { name: "Vendors", href: "/launch/vendors" },
  { name: "Competitors", href: "/launch/competitors" },
  { name: "Creatives", href: "/launch/creatives" },
  { name: "Profit check", href: "/launch/profit" },
  { name: "Launch", href: "/launch/finish" },
] as const;

export function LaunchSteps({ current }: { current: number }) {
  const { t, tf } = useLanguage();
  const project = useSearchParams().get("project");
  const step = STEPS[current - 1];
  return (
    <nav aria-label={t("Launch steps")} className="space-y-2">
      <p className="text-sm font-medium text-ink">
        {tf("Step {n} of {total}: {name}", { n: current, total: STEPS.length, name: t(step.name) })}
      </p>
      <ol className="flex flex-wrap gap-2">
        {STEPS.map((s, i) => {
          const active = i + 1 === current;
          const href = project && i > 0 ? `${s.href}?project=${encodeURIComponent(project)}` : s.href;
          return (
            <li key={s.name}>
              <Link
                href={href}
                aria-current={active ? "step" : undefined}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40",
                  active ? "border-accent text-ink" : "border-line text-ink-2 hover:border-accent/40",
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn("grid h-5 w-5 place-items-center rounded-full text-[11px] font-semibold", active ? "bg-accent text-accent-ink" : "bg-surface-3 text-muted")}
                >
                  {i + 1}
                </span>
                {t(s.name)}
              </Link>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
