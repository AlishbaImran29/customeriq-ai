"use client";

import { MessageCircle } from "lucide-react";
import { FilterPills } from "@/components/ui/filter-pills";
import { useCurrency } from "@/lib/currency";
import { useLanguage } from "@/lib/i18n";
import { whatsappLink, type MessageLanguage } from "@/lib/whatsapp";

const buttonClass =
  "inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-surface-2 px-3.5 py-2 text-sm font-medium text-ink-2 transition hover:bg-surface-3 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-app";

/** The seller chooses the language of the message that goes to the customer. */
export function MessageLanguagePicker({
  value,
  onChange,
}: {
  value: MessageLanguage;
  onChange: (value: MessageLanguage) => void;
}) {
  const { t } = useLanguage();
  return (
    <FilterPills
      label={t("Message language")}
      options={[
        { value: "en" as const, label: "English" },
        { value: "ur" as const, label: "اردو" },
      ]}
      value={value}
      onChange={onChange}
    />
  );
}

/**
 * "Confirm on WhatsApp" for a risky order. It only opens WhatsApp with the message ready (a
 * wa.me link); nothing is sent until the seller presses send there. Low-risk orders show nothing.
 *
 * `phone` is the number in international digits (made by the backend). With no usable number the
 * button is disabled and the reason is written next to it, never hidden.
 * `amount` is in the currency of the imported data, because that is what the customer pays.
 */
export function WhatsAppButton({
  level,
  orderId,
  amount,
  phone,
  messageLanguage,
  showReason = true,
}: {
  level: "Low" | "Medium" | "High";
  orderId: string;
  amount: number;
  phone: string | null;
  messageLanguage: MessageLanguage;
  /** False in a long list: the reason is then given once for the whole list, and only as a hint here. */
  showReason?: boolean;
}) {
  const { t } = useLanguage();
  const { state } = useCurrency();
  if (level === "Low") return null;

  const amountText = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: state.source,
    maximumFractionDigits: Math.abs(amount) >= 1000 ? 0 : 2,
  }).format(amount);
  const link = whatsappLink(phone, messageLanguage, orderId, amountText);
  const reasonId = `whatsapp-reason-${orderId}`;

  if (!link) {
    const reason = t("No usable phone number in the data for this customer, so WhatsApp cannot be opened.");
    return (
      <div className="flex flex-col gap-1">
        <button
          type="button"
          disabled
          aria-describedby={reasonId}
          title={reason}
          className={`${buttonClass} cursor-not-allowed opacity-50`}
        >
          <MessageCircle className="h-4 w-4" aria-hidden="true" />
          {t("Confirm on WhatsApp")}
        </button>
        <p id={reasonId} className={showReason ? "text-xs text-muted" : "sr-only"}>
          {reason}
        </p>
      </div>
    );
  }
  return (
    <a
      href={link}
      target="_blank"
      rel="noopener noreferrer"
      className={buttonClass}
      title={t("Opens WhatsApp with the message ready. Nothing is sent until you press send.")}
    >
      <MessageCircle className="h-4 w-4" aria-hidden="true" />
      {t("Confirm on WhatsApp")}
    </a>
  );
}
