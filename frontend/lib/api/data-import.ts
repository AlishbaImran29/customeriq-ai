// Customer data import service.
//
// CSVs are parsed in the browser for a quick preview. The authoritative checks
// (file type, size, columns, every row) run on the server in
// POST /api/v1/imports, which also saves the valid rows. Excel files are only
// read on the server. In demo mode (no API configured) nothing is uploaded.

import { API_MODE, apiGet, apiPostForm } from "@/lib/api/config";

export const IMPORT_ENDPOINT_AVAILABLE = API_MODE === "live";

/** Must match MAX_FILE_BYTES in backend/app/services/import_files.py. */
export const MAX_IMPORT_BYTES = 10 * 1024 * 1024;

export const ACCEPTED_EXTENSIONS = [".csv", ".xlsx"] as const;

export const REQUIRED_COLUMNS = ["order_id", "order_date", "order_value"] as const;

/** A row must say who ordered: any ONE of these columns is enough (a seller on WhatsApp has a phone, not an email). */
export const IDENTITY_COLUMNS = ["customer_id", "email", "phone"] as const;
export const IDENTITY_LABEL = "customer_id or email or phone (at least one)";

export const OPTIONAL_COLUMNS = [
  "first_name",
  "last_name",
  "country",
  "product_category",
  "channel",
  "engagement",
] as const;

export const TEMPLATE_CSV = [
  ["customer_id", "email", "order_id", "order_date", "order_value", ...OPTIONAL_COLUMNS].join(","),
  "CUS-1042,amelia.chen@example.com,ORD-88120,2026-10-08,142.50,Amelia,Chen,US,Skincare,Shopify,82",
  "CUS-1188,noah.patel@example.com,ORD-88121,2026-09-29,89.00,Noah,Patel,UK,Haircare,WooCommerce,",
].join("\n");

/** Minimal RFC 4180 CSV parser (quoted fields, escaped quotes, CRLF). */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  const input = text.replace(/^\uFEFF/, "");

  for (let i = 0; i < input.length; i++) {
    const char = input[i];
    if (inQuotes) {
      if (char === '"' && input[i + 1] === '"') {
        field += '"';
        i++;
      } else if (char === '"') {
        inQuotes = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && input[i + 1] === "\n") i++;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field !== "" || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((r) => r.some((cell) => cell.trim() !== ""));
}

/** "shopify" = Shopify orders export (Admin → Orders → Export), converted on the server. */
export type FileFormat = "standard" | "shopify";

// Must match _SHOPIFY_MARKERS in backend/app/services/import_formats.py.
const SHOPIFY_MARKERS = ["name", "email", "created_at", "total", "financial_status"];

export type CsvAnalysis = {
  format: FileFormat;
  headers: string[];
  rows: string[][];
  missingColumns: string[];
  recognisedColumns: string[];
  emptyRequiredCells: number;
  duplicateOrderIds: number;
  invalidOrderValues: number;
};

const normalise = (header: string) =>
  header.trim().toLowerCase().replace(/[\s-]+/g, "_");

export function analyseCsv(table: string[][]): CsvAnalysis {
  const [rawHeaders = [], ...rows] = table;
  const headers = rawHeaders.map(normalise);
  const index = (name: string) => headers.indexOf(name);
  const known: string[] = [...REQUIRED_COLUMNS, ...IDENTITY_COLUMNS, ...OPTIONAL_COLUMNS];

  if (!headers.includes("order_id") && SHOPIFY_MARKERS.every((m) => headers.includes(m))) {
    // Shopify rows are line items (order numbers repeat), so the standard
    // checks do not apply; the server groups and validates them.
    return {
      format: "shopify",
      headers: rawHeaders.map((h) => h.trim()),
      rows,
      missingColumns: [],
      recognisedColumns: [],
      emptyRequiredCells: 0,
      duplicateOrderIds: 0,
      invalidOrderValues: 0,
    };
  }

  let emptyRequiredCells = 0;
  for (const column of REQUIRED_COLUMNS) {
    const i = index(column);
    if (i === -1) continue;
    emptyRequiredCells += rows.filter((r) => !r[i]?.trim()).length;
  }

  // Rows that say nothing about who ordered (every identity cell empty).
  const identityColumns = IDENTITY_COLUMNS.map(index).filter((i) => i !== -1);
  if (identityColumns.length > 0) {
    emptyRequiredCells += rows.filter((r) => identityColumns.every((i) => !r[i]?.trim())).length;
  }

  const orderIndex = index("order_id");
  const seen = new Set<string>();
  let duplicateOrderIds = 0;
  if (orderIndex !== -1) {
    for (const r of rows) {
      const id = r[orderIndex]?.trim();
      if (!id) continue;
      if (seen.has(id)) duplicateOrderIds++;
      seen.add(id);
    }
  }

  const valueIndex = index("order_value");
  const invalidOrderValues =
    valueIndex === -1
      ? 0
      : rows.filter((r) => {
          const value = r[valueIndex]?.trim();
          return value !== undefined && value !== "" && Number.isNaN(Number(value));
        }).length;

  return {
    format: "standard",
    headers,
    rows,
    missingColumns: [
      ...REQUIRED_COLUMNS.filter((c) => index(c) === -1),
      ...(IDENTITY_COLUMNS.some((c) => index(c) !== -1) ? [] : [IDENTITY_LABEL]),
    ],
    recognisedColumns: headers.filter((h) => known.includes(h)),
    emptyRequiredCells,
    duplicateOrderIds,
    invalidOrderValues,
  };
}
// --- Server import (POST /api/v1/imports) ----------------------------------

export type ImportStatus = "pending" | "processing" | "completed" | "failed";

export type ImportRowError = {
  /** Row number as shown in Excel (header is row 1). */
  row: number | null;
  column: string | null;
  message: string;
};

/** Response of POST /api/v1/imports and GET /api/v1/imports/{id}. */
export type ImportResult = {
  id: string;
  filename: string;
  fileType: "csv" | "xlsx";
  fileFormat: FileFormat;
  /** Data rows in the file (Shopify: one per line item, grouped into orders). */
  rowsInFile: number;
  status: ImportStatus;
  rowsReceived: number;
  /** New orders saved. */
  rowsImported: number;
  /** Existing orders (same order_id) overwritten with this file's values. */
  rowsUpdated: number;
  rowsRejected: number;
  errorCount: number;
  errors: ImportRowError[];
  /** True when more errors exist than are listed in `errors`. */
  errorsTruncated: boolean;
  createdAt: string;
  completedAt: string | null;
};

export type ImportSummary = Omit<ImportResult, "errors" | "errorsTruncated">;

export function uploadImport(file: File): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<ImportResult>("/api/v1/imports", form);
}

export function listImports(limit = 10): Promise<ImportSummary[]> {
  return apiGet<ImportSummary[]>(`/api/v1/imports?limit=${limit}`);
}

// --- Courier results (Order Risk) -------------------------------------------------------------

export type CourierImportResult = {
  rowsInFile: number;
  rowsUpdated: number;
  rowsReturned: number;
  rowsRejected: number;
  errorCount: number;
  errors: { row: number | null; column: string | null; message: string }[];
  errorsTruncated: boolean;
};

/** POST /api/v1/imports/courier: columns order_id, customer_id, status (delivered/returned), date. */
export function uploadCourierFile(file: File): Promise<CourierImportResult> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<CourierImportResult>("/api/v1/imports/courier", form);
}
