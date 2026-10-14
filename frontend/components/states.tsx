import type { LucideIcon } from "lucide-react";
import { AlertTriangle, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
  className,
}: {
  title: string;
  description?: string;
  icon?: LucideIcon;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 px-6 py-10 text-center",
        className,
      )}
    >
      <div className="rounded-xl bg-white p-2.5 text-slate-400 shadow-sm">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </div>
      <p className="mt-3 text-sm font-medium text-slate-900">{title}</p>
      {description ? (
        <p className="mt-1 max-w-sm text-sm text-slate-500">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  description,
  action,
  className,
}: {
  title?: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center rounded-2xl border border-rose-200 bg-rose-50/60 px-6 py-10 text-center",
        className,
      )}
    >
      <div className="rounded-xl bg-white p-2.5 text-rose-600 shadow-sm">
        <AlertTriangle className="h-5 w-5" aria-hidden="true" />
      </div>
      <p className="mt-3 text-sm font-medium text-slate-900">{title}</p>
      {description ? (
        <p className="mt-1 max-w-md text-sm text-slate-600">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}