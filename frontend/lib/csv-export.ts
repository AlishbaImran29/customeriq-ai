// Builds and downloads a CSV file in the browser (nothing is sent anywhere).

type Cell = string | number | null | undefined;

function escapeCell(value: Cell): string {
  if (value === null || value === undefined) return "";
  let text = String(value);
  // Spreadsheets run cells that start with = + - @ as formulas; a leading quote keeps text as text.
  // Real numbers are written as-is, so negative amounts stay numbers.
  if (typeof value === "string" && /^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(header: string[], rows: Cell[][]): string {
  return [header, ...rows].map((row) => row.map(escapeCell).join(",")).join("\r\n");
}

export function downloadCsv(filename: string, header: string[], rows: Cell[][]) {
  // The BOM makes Excel read non-English names (Urdu, Arabic, Chinese…) correctly.
  const blob = new Blob(["﻿", toCsv(header, rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
