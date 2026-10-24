// Quick Order Entry service (browser side): look a customer up by phone, and save one order.
// Both calls go through this site's own /api/v1/... path (see lib/api/config.ts).

import { API_MODE, apiGet, apiPostJson } from "@/lib/api/config";

export const QUICK_ORDER_AVAILABLE = API_MODE === "live";

/** GET /api/v1/customers/lookup: what the phone box shows while the seller types. */
export type CustomerLookup = {
  /** The text is a Pakistani mobile number. */
  valid: boolean;
  /** +923XXXXXXXXX when valid. */
  phone: string | null;
  found: boolean;
  name: string | null;
  orders: number;
  lastOrderDate: string | null;
  lastCity: string | null;
};

export function lookupCustomer(phone: string, signal?: AbortSignal): Promise<CustomerLookup> {
  return apiGet<CustomerLookup>(`/api/v1/customers/lookup?phone=${encodeURIComponent(phone)}`, { signal });
}

export type QuickOrderRequest = {
  customerName: string;
  phone: string;
  city: string;
  products: string[];
  amount: number;
  paymentType: string;
  channel: string;
  /** With channel "other": the platform's own name, e.g. TikTok. */
  platform?: string;
  /** The courier the parcel goes with (optional); a shipment is created for it. */
  courier?: string;
  orderDate: string;
  note: string | null;
  /** The customer agreed to WhatsApp order updates (Auto Messenger). Leave out when they did not say. */
  whatsappOk?: boolean;
};

export type QuickOrderResponse = {
  orderId: string;
  customerId: string;
  customerName: string;
  phone: string;
  /** The number already belonged to a customer. */
  returning: boolean;
  /** That customer's orders, including this one. */
  customerOrders: number;
};

/** POST /api/v1/orders. A 422 carries `details.fields` (field name -> message). */
export function createQuickOrder(order: QuickOrderRequest): Promise<QuickOrderResponse> {
  return apiPostJson<QuickOrderResponse>("/api/v1/orders", order);
}
