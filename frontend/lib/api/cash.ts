// Cash Tracker service (browser side): COD money the couriers still owe, and their payments.

import { API_MODE, apiDelete, apiGet, apiPostForm, apiPostJson } from "@/lib/api/config";

export const CASH_AVAILABLE = API_MODE === "live";

/** Must match MAX_FILE_BYTES in backend/app/api/v1/shipments.py (Vercel accepts bodies of at most 4.5 MB). */
export const MAX_PAYMENT_BYTES = 4 * 1024 * 1024;

export type CourierCash = {
  courier: string;
  deliveredCod: number;
  received: number;
  pending: number;
  /** Pending + partly paid parcels. */
  unpaidParcels: number;
  paidParcels: number;
  oldestPendingDays: number | null;
  /** null without enough fully paid parcels (the minimum-count rule). */
  averageDaysToPay: number | null;
  enough: boolean;
  needed: number;
  credit: number;
  overdueAmount: number;
  overdueParcels: number;
};

export type AgeBucket = { label: string; parcels: number; amount: number };

export type CashTracker = {
  asOf: string;
  alertDays: number;
  /** "real", or "demo" when only made-up data exists. */
  sourceUsed: string;
  realCodParcels: number;
  demoCodParcels: number;
  payments: number;
  minGroupCount: number;
  deliveredCod: number;
  received: number;
  pending: number;
  credit: number;
  unpaidParcels: number;
  oldestPendingDays: number | null;
  couriers: CourierCash[];
  buckets: AgeBucket[];
  alerts: CourierCash[];
};

export type PendingRow = {
  courier: string;
  city: string | null;
  reference: string;
  deliveredOn: string;
  daysPending: number;
  codAmount: number;
  paid: number;
  stillOwed: number;
  status: "pending" | "partly_paid";
};

export type PaymentImportResult = {
  rowsInFile: number;
  created: number;
  updated: number;
  rejected: number;
  newCourierNames: string[];
  errorCount: number;
  errors: { row: number | null; column: string | null; message: string }[];
  errorsTruncated: boolean;
};

export type PaymentsSummary = { payments: number; demoPayments: number };

export function getCashTracker(alertDays: number): Promise<CashTracker> {
  return apiGet<CashTracker>(`/api/v1/cash/tracker?alert_days=${alertDays}`);
}

export function getPendingParcels(): Promise<PendingRow[]> {
  return apiGet<PendingRow[]>("/api/v1/cash/pending");
}

export function uploadPayments(file: File): Promise<PaymentImportResult> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<PaymentImportResult>("/api/v1/cash/payments/import", form);
}

export type PaymentInput = { courierName: string; paymentDate: string; amount: number; reference?: string; orderIds?: string };

export function addPayment(input: PaymentInput): Promise<{ courier: string; paymentDate: string; amount: number }> {
  return apiPostJson("/api/v1/cash/payments", input);
}

export function getPaymentsSummary(): Promise<PaymentsSummary> {
  return apiGet<PaymentsSummary>("/api/v1/cash/payments/summary");
}

/** DELETE /api/v1/cash/payments/demo: only the made-up payments; real ones are never touched. */
export function deleteDemoPayments(): Promise<{ deleted: number }> {
  return apiDelete<{ deleted: number }>("/api/v1/cash/payments/demo");
}
