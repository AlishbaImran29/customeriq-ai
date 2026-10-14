import { cn } from "@/lib/utils";

const variants: Record<string, string> = {
  default: "bg-slate-100 text-slate-700",
  success: "bg-emerald-50 text-emerald-700",
  warning: "bg-amber-50 text-amber-800",
  serious: "bg-orange-50 text-orange-800",
  danger: "bg-rose-50 text-rose-700",
  info: "bg-sky-50 text-sky-800",
  brand: "bg-teal-50 text-teal-800",
};

export function Badge({
  className,
  variant = "default",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { variant?: keyof typeof variants }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}

export function riskVariant(level: string) {
  if (level === "Low") return "success" as const;
  if (level === "Medium") return "warning" as const;
  if (level === "High") return "serious" as const;
  return "danger" as const;
}

export function impactVariant(level: string) {
  if (level === "High") return "brand" as const;
  if (level === "Medium") return "info" as const;
  return "default" as const;
}
