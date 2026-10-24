"use client";

import { Ban, Check, CheckCheck, CircleX, Clock, Eye, Hourglass, MessageCircle, Reply, Send, ShieldCheck, ShieldOff, ShieldQuestion } from "lucide-react";
import { EmptyState } from "@/components/states";
import { MESSENGER_AVAILABLE, type ConsentState, type MessageStatus } from "@/lib/api/messaging";
import { useLanguage } from "@/lib/i18n";
import { reasonPhrase } from "@/lib/messenger-text";
import { cn } from "@/lib/utils";

/** The page body only when the backend is connected: Auto Messenger saves everything in the database. */
export function MessengerGate({ children }: { children: React.ReactNode }) {
  const { t } = useLanguage();
  if (!MESSENGER_AVAILABLE) {
    return (
      <EmptyState
        icon={MessageCircle}
        title={t("Auto Messenger needs the backend")}
        description={t("Messages, consent and templates are saved in your database. Connect the backend to use Auto Messenger.")}
      />
    );
  }
  return <>{children}</>;
}

const STATUS_LOOK: Record<MessageStatus, { label: string; icon: typeof Send; className: string }> = {
  queued: { label: "Waiting", icon: Hourglass, className: "bg-info/10 text-info" },
  sent: { label: "Sent", icon: Send, className: "bg-surface-3 text-ink-2" },
  delivered: { label: "Delivered", icon: Check, className: "bg-success/10 text-success" },
  read: { label: "Read", icon: CheckCheck, className: "bg-success/10 text-success" },
  replied: { label: "Replied", icon: Reply, className: "bg-accent/10 text-accent" },
  failed: { label: "Failed", icon: CircleX, className: "bg-danger/10 text-danger" },
  skipped: { label: "Not sent", icon: Ban, className: "bg-warning/10 text-warning" },
};

/** A message status as an icon AND a word, never colour alone. */
export function MessageStatusBadge({ status }: { status: MessageStatus }) {
  const { t } = useLanguage();
  const look = STATUS_LOOK[status];
  const Icon = look.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium", look.className)}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      {t(look.label)}
    </span>
  );
}

/** Why a message was not sent, in plain words. Renders nothing when there is no reason. */
export function Reason({ code }: { code: string | null | undefined }) {
  const { t, tf } = useLanguage();
  const phrase = reasonPhrase(code);
  if (!phrase) return null;
  return <>{phrase.params ? tf(phrase.text, phrase.params) : t(phrase.text)}</>;
}

const CONSENT_LOOK: Record<ConsentState, { label: string; icon: typeof ShieldCheck; className: string }> = {
  opted_in: { label: "Agreed", icon: ShieldCheck, className: "bg-success/10 text-success" },
  opted_out: { label: "Stopped", icon: ShieldOff, className: "bg-danger/10 text-danger" },
  none: { label: "Not asked", icon: ShieldQuestion, className: "bg-surface-3 text-muted" },
};

export function ConsentBadge({ state }: { state: ConsentState }) {
  const { t } = useLanguage();
  const look = CONSENT_LOOK[state];
  const Icon = look.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium", look.className)}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      {t(look.label)}
    </span>
  );
}

/** "AI draft" label: AI text is always marked, and the seller can edit it before anything is used. */
export function AiDraftLabel({ children }: { children?: React.ReactNode }) {
  const { t } = useLanguage();
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted">
      <span className="rounded-full bg-accent/10 px-2 py-0.5 font-medium text-accent">{t("AI draft")}</span>
      {children}
    </span>
  );
}

export function DryRunTag({ show }: { show: boolean }) {
  const { t } = useLanguage();
  if (!show) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-[11px] font-medium text-warning">
      <Clock className="h-3 w-3" aria-hidden="true" />
      {t("Dry run: not really sent")}
    </span>
  );
}

export function EyeLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1">
      <Eye className="h-3.5 w-3.5" aria-hidden="true" />
      {children}
    </span>
  );
}

export function formatWhen(value: string | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export const fieldClass = "space-y-1 text-xs font-medium text-muted";
export const areaClass =
  "min-h-24 w-full rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-faint outline-none transition focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";
