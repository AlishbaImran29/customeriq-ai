import { cn } from "@/lib/utils";

const variants = {
  primary:
    "bg-accent text-accent-ink hover:bg-accent-strong shadow-sm",
  secondary:
    "bg-surface-2 text-ink-2 border border-line hover:bg-surface-3 hover:text-ink",
  ghost: "text-ink-2 hover:bg-surface-3 hover:text-ink",
};

export function Button({
  className,
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof variants;
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl px-3.5 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-app disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
