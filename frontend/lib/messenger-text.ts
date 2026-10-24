// Plain-language text for the codes the Auto Messenger server records. No imports, so it can be tested on its own
// (messenger-text.test.ts). The strings are English; the pages pass them through the translation system.

export type Phrase = { text: string; params?: Record<string, string | number> };

const REASONS: Record<string, string> = {
  no_consent: "The customer has not agreed to be messaged.",
  opted_out: "The customer stopped these messages.",
  template_not_approved: "The template is not approved by you yet.",
  meta_template_not_approved: "Meta has not approved this template yet, so WhatsApp cannot start the chat.",
  no_phone: "There is no usable phone number.",
  no_email: "There is no usable email address.",
  weekly_cap: "The weekly limit of marketing messages was reached.",
  no_unsubscribe_link: "No unsubscribe link is set up, so a marketing email cannot be sent.",
  template_removed: "The template was deleted.",
  customer_removed: "The customer was deleted.",
  campaign_cancelled: "The campaign was cancelled.",
  no_template: "There is no template for this segment.",
  not_configured: "WhatsApp or file storage is not set up yet.",
  whatsapp_not_configured: "WhatsApp is not connected yet.",
  whatsapp_network: "WhatsApp could not be reached. It will be tried again.",
  whatsapp_no_id: "WhatsApp did not confirm the message.",
  email_timeout: "The email service did not answer in time. It will be tried again.",
  email_sender_refused: "The email service refused the sender address.",
  email_login_refused: "The email service refused the login.",
  email_address_refused: "The email address was refused.",
  email_provider_limit: "The email service limit was reached.",
  file_type: "This file type is not allowed.",
  too_large: "The file is too large.",
  media_not_found: "WhatsApp no longer has this file.",
  not_really_video: "The file is not really a video.",
  not_really_image: "The file is not really a picture.",
  empty_file: "The file is empty.",
  no_download_link: "WhatsApp gave no download link.",
  ordered_again: "The customer ordered again.",
  replied: "The customer replied.",
  segment_changed: "The customer moved to another segment.",
  same_status: "The order already has this status.",
  not_forward: "The status went back, so the customer was not messaged.",
  too_old: "The change is too old to tell the customer about.",
  not_requested: "You chose not to message the customer.",
};

export function reasonPhrase(code: string | null | undefined): Phrase | null {
  if (!code) return null;
  if (code.startsWith("missing_variable:")) return { text: "A value is missing: {name}.", params: { name: code.slice("missing_variable:".length) } };
  const whatsapp = /^whatsapp_(\d+)$/.exec(code);
  if (whatsapp) return { text: "WhatsApp refused it (code {code}).", params: { code: whatsapp[1] } };
  const email = /^email_(.+)$/.exec(code);
  if (email && !REASONS[code]) return { text: "The email could not be sent ({code}).", params: { code: email[1] } };
  return REASONS[code] ? { text: REASONS[code] } : { text: "Reason: {code}.", params: { code } };
}

const EVENTS: Record<string, string> = {
  order_confirmed: "Order confirmed",
  order_dispatched: "Order dispatched",
  order_in_transit: "Order in transit",
  order_out_for_delivery: "Order out for delivery",
  order_delivered: "Order delivered",
  order_returned: "Order returned",
  delivered_unboxing: "Unboxing video request",
  media_share_question: "May we share your video?",
  review_request: "Review request",
  journey_champions: "Champions: thank you",
  journey_loyal: "Loyal customers: what is new",
  journey_potential_1: "New customers: day 7",
  journey_potential_2: "New customers: day 21",
  journey_at_risk_1: "At-Risk: win-back",
  journey_at_risk_2: "At-Risk: check-in",
  journey_at_risk_3: "At-Risk: last note",
  journey_lost: "Lost customers: reminder",
};

/** The name of an automatic message ("order_dispatched" -> "Order dispatched"); anything unknown is shown as typed. */
export function eventLabel(event: string | null | undefined): string {
  if (!event) return "Other";
  if (EVENTS[event]) return EVENTS[event];
  if (/^campaign_\d+$/.test(event)) return "Product announcement";
  return event;
}

/** 0.1234 -> "12.3%" (one decimal, no rounding surprises for small shares). */
export function percentText(share: number | null | undefined, digits = 1): string {
  return share === null || share === undefined ? "-" : `${(share * 100).toFixed(digits)}%`;
}

/** The gap between two shares in percentage POINTS with a sign: 0.14 -> "+14.0 points". */
export function pointsText(difference: number | null | undefined): string {
  if (difference === null || difference === undefined) return "-";
  const points = difference * 100;
  return `${points >= 0 ? "+" : "-"}${Math.abs(points).toFixed(1)}`;
}
