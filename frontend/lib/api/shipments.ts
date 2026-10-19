// Courier shipments service (browser side): import a sheet of parcels, see what is saved, and remove demo data.

import { API_MODE, apiDelete, apiGet, apiPostForm } from "@/lib/api/config";

export const SHIPMENTS_AVAILABLE = API_MODE === "live";

/** Must match MAX_FILE_BYTES in backend/app/api/v1/shipments.py (Vercel accepts bodies of at most 4.5 MB). */
export const MAX_SHIPMENT_BYTES = 4 * 1024 * 1024;

export type ShipmentImportResult = {
  rowsInFile: number;
  created: number;
  updated: number;
  rejected: number;
  linkedToOrders: number;
  unlinked: number;
  /** Orders that received the courier's result (delivered or returned). */
  ordersUpdated: number;
  /** Names not in the courier / city lists: kept as typed. */
  newCourierNames: string[];
  newCityNames: string[];
  errorCount: number;
  errors: { row: number | null; column: string | null; message: string }[];
  errorsTruncated: boolean;
};

/** POST /api/v1/shipments/import */
export function uploadShipments(file: File): Promise<ShipmentImportResult> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<ShipmentImportResult>("/api/v1/shipments/import", form);
}

export type ShipmentSummary = {
  shipments: number;
  linkedToOrders: number;
  /** Made-up shipments (marked "demo (synthetic)"). */
  demoShipments: number;
  /** Standard names plus any courier already in the data, for the suggestions in forms. */
  couriers: string[];
  cities: string[];
};

export function getShipmentSummary(): Promise<ShipmentSummary> {
  return apiGet<ShipmentSummary>("/api/v1/shipments/summary");
}

/** DELETE /api/v1/shipments/demo: only the made-up shipments; real ones are never touched. */
export function deleteDemoShipments(): Promise<{ deleted: number }> {
  return apiDelete<{ deleted: number }>("/api/v1/shipments/demo");
}
