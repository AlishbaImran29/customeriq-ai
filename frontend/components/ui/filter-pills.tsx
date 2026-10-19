"use client";

import { cn } from "@/lib/utils";

/** Single-select pill group used for in-page filters. */
export function FilterPills<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  /** Accessible group label. */
  label: string;
  options: readonly { value: T; label: React.ReactNode; count?: number }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40",
              active
                ? "border-accent bg-accent text-accent-ink"
                : "border-line bg-surface-2 text-ink-2 hover:border-accent/40 hover:text-accent",
            )}
          >
            {option.label}
            {option.count !== undefined ? (
              <span
                className={cn(
                  "rounded-full px-1.5 text-[10px]",
                  active ? "bg-white/20" : "bg-surface-3 text-muted",
                )}
              >
                {option.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}