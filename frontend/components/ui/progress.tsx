import { cn } from "@/lib/utils";

const tones = {
  brand: "bg-teal-600",
  good: "bg-emerald-600",
  warning: "bg-amber-500",
  critical: "bg-rose-600",
};

export function scoreTone(score: number): keyof typeof tones {
  if (score >= 75) return "good";
  if (score >= 55) return "brand";
  if (score >= 30) return "warning";
  return "critical";
}

export function Progress({
  value,
  max = 100,
  label,
  tone = "brand",
  className,
}: {
  value: number;
  max?: number;
  /** Accessible name for the bar. */
  label: string;
  tone?: keyof typeof tones;
  className?: string;
}) {
  const percent = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      className={cn("h-2 w-full overflow-hidden rounded-full bg-slate-100", className)}
    >
      <div
        className={cn("h-full rounded-full transition-[width]", tones[tone])}
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}