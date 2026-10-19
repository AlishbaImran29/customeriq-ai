// Quick Order Entry: the choices, the checks and the "remember what I used last" helpers.
//
// This file has no imports on purpose, so it can be tested on its own (lib/quick-order.test.ts).
// The server checks everything again (backend/app/services/quick_order.py); the checks here exist
// so a seller sees a problem straight away, before pressing Save.

export const CHANNELS = [
  { value: "instagram", label: "Instagram" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "facebook", label: "Facebook" },
  { value: "website", label: "Website" },
  { value: "other", label: "Other" },
] as const;
export type Channel = (typeof CHANNELS)[number]["value"];

export const PAYMENT_TYPES = [
  { value: "cod", label: "Cash on delivery (COD)" },
  { value: "prepaid", label: "Prepaid" },
] as const;
export type PaymentType = (typeof PAYMENT_TYPES)[number]["value"];

/** Cities offered while typing. Any city can still be typed. */
export const PK_CITIES = [
  "Karachi", "Lahore", "Islamabad", "Rawalpindi", "Faisalabad", "Multan", "Peshawar", "Quetta",
  "Hyderabad", "Sialkot", "Gujranwala", "Bahawalpur", "Sargodha", "Sukkur", "Larkana", "Mardan",
  "Abbottabad", "Gujrat", "Sahiwal", "Rahim Yar Khan", "Sheikhupura", "Jhang", "Dera Ghazi Khan",
  "Mirpur", "Muzaffarabad",
];

/** Platforms offered while typing under "Other". Any name can still be typed. */
export const PLATFORM_SUGGESTIONS = ["TikTok", "Daraz", "OLX", "Snapchat", "Telegram", "YouTube", "Walk-in", "Phone call"];
export const MAX_PLATFORM = 50;

export const MAX_AMOUNT = 9_999_999.99;
export const MAX_PRODUCTS = 20;

export type FormValues = {
  phone: string;
  customerName: string;
  city: string;
  /** Products already added as chips. */
  products: string[];
  /** Text typed in the product box and not added yet: it still counts when saving. */
  productInput: string;
  amount: string;
  paymentType: PaymentType | "";
  channel: Channel | "";
  /** With channel "other": the platform's own name, e.g. TikTok. */
  platform: string;
  orderDate: string;
  note: string;
};

export type FieldName = "phone" | "customerName" | "city" | "products" | "amount" | "paymentType" | "channel" | "platform" | "orderDate" | "note";
export type FieldErrors = Partial<Record<FieldName, string>>;

/** Add a product to the list: trimmed, and ignored when empty or already there (any capitals). */
export function addProduct(products: readonly string[], text: string): string[] {
  const name = text.trim().replace(/\s+/g, " ");
  if (!name || products.some((p) => p.toLowerCase() === name.toLowerCase())) return [...products];
  return [...products, name];
}

/** Several products can be typed or pasted at once, separated by commas or new lines. */
export function addProducts(products: readonly string[], text: string): string[] {
  return text.split(/[,\n]/).reduce((list, part) => addProduct(list, part), [...products]);
}

/** The amount as a number, or null when it is not one ("2,500" is fine). */
export function parseAmount(text: string): number | null {
  const cleaned = text.replace(/,/g, "").trim();
  if (cleaned === "" || !/^\d*\.?\d+$|^\d+\.$/.test(cleaned)) return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

/** The checks, with messages that go through the translation table. Empty object = all good. */
export function validate(values: FormValues, today: string): FieldErrors {
  const errors: FieldErrors = {};
  if (!values.phone.trim()) errors.phone = "Enter the customer's phone number.";
  if (!values.customerName.trim()) errors.customerName = "Enter the customer's name.";
  else if (values.customerName.trim().length > 100) errors.customerName = "The name is too long (100 characters at most).";
  if (!values.city.trim()) errors.city = "Enter the city.";
  const products = addProducts(values.products, values.productInput);
  if (products.length === 0) errors.products = "Add at least one product.";
  else if (products.length > MAX_PRODUCTS) errors.products = "Add at most 20 products.";

  if (values.amount.trim() === "") errors.amount = "Enter the amount.";
  else {
    const amount = parseAmount(values.amount);
    if (amount === null) errors.amount = "Enter the amount as a number, like 2500.";
    else if (amount <= 0) errors.amount = "The amount must be more than 0.";
    else if (amount > MAX_AMOUNT) errors.amount = "The amount is too large.";
  }
  if (!values.paymentType) errors.paymentType = "Choose COD or prepaid.";
  if (!values.channel) errors.channel = "Choose where the order came from.";
  if (values.channel === "other" && values.platform.trim().length > MAX_PLATFORM) {
    errors.platform = "The platform name is too long (50 characters at most).";
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(values.orderDate)) errors.orderDate = "Enter the date as YYYY-MM-DD.";
  else if (values.orderDate > today) errors.orderDate = "The date is in the future.";
  if (values.note.length > 500) errors.note = "The note is too long (500 characters at most).";
  return errors;
}

/** The first field with a problem, in the order the form shows them (to move the cursor there). */
export const FIELD_ORDER: FieldName[] = ["phone", "customerName", "city", "products", "amount", "paymentType", "channel", "platform", "orderDate", "note"];
export function firstError(errors: FieldErrors): FieldName | null {
  return FIELD_ORDER.find((name) => errors[name]) ?? null;
}

// --- remember what was used last, to make the next order faster -------------------------------

export type LastUsed = { channel: Channel | ""; platform: string; paymentType: PaymentType | ""; products: string[] };
export const LAST_USED_KEY = "ciq_quick_order_last";

type Storage = Pick<globalThis.Storage, "getItem" | "setItem">;

export function saveLastUsed(storage: Storage, used: LastUsed) {
  try {
    storage.setItem(LAST_USED_KEY, JSON.stringify(used));
  } catch {
    // Storage blocked or full: the next order just starts empty.
  }
}

/** What was used last on this device. Anything unreadable or unexpected is ignored, never trusted. */
export function loadLastUsed(storage: Storage): LastUsed {
  const empty: LastUsed = { channel: "", platform: "", paymentType: "", products: [] };
  try {
    const raw = JSON.parse(storage.getItem(LAST_USED_KEY) ?? "null");
    if (!raw || typeof raw !== "object") return empty;
    const channel = CHANNELS.some((c) => c.value === raw.channel) ? raw.channel : "";
    const paymentType = PAYMENT_TYPES.some((p) => p.value === raw.paymentType) ? raw.paymentType : "";
    const products = Array.isArray(raw.products)
      ? raw.products.filter((p: unknown): p is string => typeof p === "string" && p.trim() !== "" && p.length <= 100).slice(0, MAX_PRODUCTS)
      : [];
    const platform = typeof raw.platform === "string" ? raw.platform.trim().slice(0, MAX_PLATFORM) : "";
    return { channel, platform, paymentType, products };
  } catch {
    return empty;
  }
}

/** Today's date on the seller's own device, as YYYY-MM-DD. */
export function localToday(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}
