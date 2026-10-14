// Customer data import service.
//
// Files are validated and CSVs are parsed in the browser for preview only.
// Nothing is uploaded: the import endpoint (POST /api/v1/imports) does not
// exist yet. Excel parsing will happen server-side once it does.

export const IMPORT_ENDPOINT_AVAILABLE = false;

export const MAX_IMPORT_BYTES = 10 * 1024 * 1024;

export const ACCEPTED_EXTENSIONS = [".csv", ".xlsx", ".xls"] as const;

export const REQUIRED_COLUMNS = [
  "customer_id",
  "email",
  "order_id",
  "order_date",
  "order_value",
] as const;

export const OPTIONAL_COLUMNS = [
  "first_name",
  "last_name",
  "country",
  "product_category",
  "channel",
] as const;

export const TEMPLATE_CSV = [
  [...REQUIRED_COLUMNS, ...OPTIONAL_COLUMNS].join(","),
  "CUS-1042,amelia.chen@example.com,ORD-88120,2026-10-08,142.50,Amelia,Chen,US,Skincare,Shopify",
  "CUS-1188,noah.patel@example.com,ORD-88121,2026-09-29,89.00,Noah,Patel,UK,Haircare,WooCommerce",
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

export type CsvAnalysis = {
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
  const known: string[] = [...REQUIRED_COLUMNS, ...OPTIONAL_COLUMNS];

  let emptyRequiredCells = 0;
  for (const column of REQUIRED_COLUMNS) {
    const i = index(column);
    if (i === -1) continue;
    emptyRequiredCells += rows.filter((r) => !r[i]?.trim()).length;
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
    headers,
    rows,
    missingColumns: REQUIRED_COLUMNS.filter((c) => index(c) === -1),
    recognisedColumns: headers.filter((h) => known.includes(h)),
    emptyRequiredCells,
    duplicateOrderIds,
    invalidOrderValues,
  };
}