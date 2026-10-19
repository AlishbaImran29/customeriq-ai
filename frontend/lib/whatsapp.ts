// WhatsApp confirmation link for risky orders. No paid API and no server: the button only
// opens a "wa.me" link, with the message already typed. Nothing is sent until the seller
// presses send inside WhatsApp.
//
// This file has no imports on purpose, so it can be tested on its own (lib/whatsapp.test.ts).

export type MessageLanguage = "en" | "ur";

/** Digits of an international number, as made by the backend (backend/app/services/whatsapp.py). */
const INTERNATIONAL_DIGITS = /^[1-9]\d{7,14}$/;

/**
 * The text sent to the customer. It is for the customer, so its language is chosen by the seller
 * (English or Urdu), not by the interface language. `amountText` is already formatted, in the
 * currency the order was placed in.
 */
export function whatsappMessage(language: MessageLanguage, orderId: string, amountText: string): string {
  if (language === "ur") {
    return (
      `السلام علیکم! ہمیں آپ کا آرڈر ${orderId} (رقم ${amountText}) موصول ہوا ہے۔ ` +
      `براہِ کرم تصدیق کے لیے "ہاں" لکھ کر جواب دیں، پھر ہم اسے بھیج دیں گے۔ شکریہ!`
    );
  }
  return (
    `Hello! We received your order ${orderId} for ${amountText}. ` +
    `Please reply YES to confirm it and we will ship it. Thank you!`
  );
}

/**
 * The wa.me link with the message prefilled, or null when there is no usable phone number
 * (the caller then shows a disabled button and says why).
 */
export function whatsappLink(
  phoneDigits: string | null | undefined,
  language: MessageLanguage,
  orderId: string,
  amountText: string,
): string | null {
  if (!phoneDigits || !INTERNATIONAL_DIGITS.test(phoneDigits)) return null;
  return `https://wa.me/${phoneDigits}?text=${encodeURIComponent(whatsappMessage(language, orderId, amountText))}`;
}
