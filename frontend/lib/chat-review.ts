// The review screen for a WhatsApp chat import: one row per suggested order, which the seller
// accepts, edits or rejects. Nothing is saved until the seller accepts, and what is saved carries
// no chat text.
//
// No imports except the order checks, so it can be tested on its own (lib/chat-review.test.ts).

import { addProducts, parseAmount, validate, type FieldErrors } from "./quick-order.ts";

export type ReviewCandidate = {
  id: number;
  customerName: string;
  phone: string | null;
  city: string | null;
  amount: number | null;
  paymentType: "cod" | "prepaid" | null;
  orderDate: string;
  orderTime: string;
};

/** What the seller sees and edits for one order. Everything is text, as typed into the fields. */
export type RowValues = {
  customerName: string;
  phone: string;
  city: string;
  products: string[];
  productInput: string;
  amount: string;
  paymentType: "cod" | "prepaid" | "";
  orderDate: string;
};

export type RowStatus = "pending" | "accepted" | "rejected";

export type ReviewRow = {
  candidate: ReviewCandidate;
  status: RowStatus;
  values: RowValues;
  errors: FieldErrors;
};

/** The suggested order as editable values. Products are never guessed: the seller types them. */
export function rowFrom(candidate: ReviewCandidate): ReviewRow {
  return {
    candidate,
    status: "pending",
    errors: {},
    values: {
      customerName: candidate.customerName,
      phone: candidate.phone ?? "",
      city: candidate.city ?? "",
      products: [],
      productInput: "",
      amount: candidate.amount === null ? "" : String(candidate.amount),
      paymentType: candidate.paymentType ?? "",
      orderDate: candidate.orderDate,
    },
  };
}

/** The same checks as the Add Order form (the channel is always WhatsApp). */
export function checkRow(values: RowValues, today: string): FieldErrors {
  return validate({ ...values, channel: "whatsapp", note: "" }, today);
}

/** Accept: only when every field is valid. Otherwise the row stays open with its problems. */
export function accept(row: ReviewRow, today: string): ReviewRow {
  const errors = checkRow(row.values, today);
  if (Object.keys(errors).length > 0) return { ...row, errors, status: "pending" };
  return { ...row, errors: {}, status: "accepted" };
}

export const reject = (row: ReviewRow): ReviewRow => ({ ...row, status: "rejected", errors: {} });
export const reopen = (row: ReviewRow): ReviewRow => ({ ...row, status: "pending", errors: {} });

export type AcceptedRow = {
  customerName: string;
  phone: string;
  city: string;
  products: string[];
  amount: number;
  paymentType: string;
  orderDate: string;
  messageTime: string;
};

/** The fields saved for an accepted row: no chat text, and no field that was not typed or accepted. */
export function toAccepted(row: ReviewRow): AcceptedRow {
  const v = row.values;
  return {
    customerName: v.customerName.trim(),
    phone: v.phone.trim(),
    city: v.city.trim(),
    products: addProducts(v.products, v.productInput),
    amount: parseAmount(v.amount) ?? 0,
    paymentType: v.paymentType,
    orderDate: v.orderDate,
    messageTime: row.candidate.orderTime,
  };
}

export function counts(rows: readonly ReviewRow[]) {
  return {
    pending: rows.filter((r) => r.status === "pending").length,
    accepted: rows.filter((r) => r.status === "accepted").length,
    rejected: rows.filter((r) => r.status === "rejected").length,
  };
}

export const acceptedRows = (rows: readonly ReviewRow[]) => rows.filter((r) => r.status === "accepted").map(toAccepted);
