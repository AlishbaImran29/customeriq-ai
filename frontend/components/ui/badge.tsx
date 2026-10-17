import { CircleAlert, CircleCheck, OctagonAlert, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";

const variants: Record<string, string> = {
  default: "bg-surface-3 text-ink-2",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  serious: "bg-serious/10 text-serious",
  danger: "bg-danger/10 text-danger",
  info: "bg-info/10 text-info",
  brand: "bg-accent/10 text-accent",
};

// A distinct shape per status so the meaning never depends on colour alone.
const icons: Record<string, typeof CircleCheck> = {
  success: CircleCheck,
  warning: CircleAlert,
  serious: TriangleAlert,
  danger: OctagonAlert,
};

export function Badge({
  className,
  variant = "default",
  children,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { variant?: keyof typeof variants }) {
  const Icon = icons[variant as string];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        variants[variant],
        className,
      )}
      {...props}
    >
      {Icon ? <Icon className="h-3 w-3 shrink-0" aria-hidden="true" /> : null}
      {children}
    </span>
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
