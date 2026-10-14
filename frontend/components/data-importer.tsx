"use client";

import { useRef, useState } from "react";
import {
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Loader2,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";
import { EmptyState, ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ACCEPTED_EXTENSIONS,
  IMPORT_ENDPOINT_AVAILABLE,
  MAX_IMPORT_BYTES,
  REQUIRED_COLUMNS,
  TEMPLATE_CSV,
  analyseCsv,
  parseCsv,
  type CsvAnalysis,
} from "@/lib/api/data-import";
import { cn, formatNumber } from "@/lib/utils";

type ImportState =
  | { status: "idle" }
  | { status: "reading"; file: File }
  | { status: "error"; message: string }
  | { status: "csv"; file: File; analysis: CsvAnalysis }
  | { status: "excel"; file: File };

const PREVIEW_ROWS = 8;

function extensionOf(name: string) {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DataImporter() {
  const [state, setState] = useState<ImportState>({ status: "idle" });
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    const ext = extensionOf(file.name);
    if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(ext)) {
      setState({ status: "error", message: `"${file.name}" is not a CSV or Excel file. Accepted formats: ${ACCEPTED_EXTENSIONS.join(", ")}.` });
      return;
    }
    if (file.size === 0) {
      setState({ status: "error", message: `"${file.name}" is empty.` });
      return;
    }
    if (file.size > MAX_IMPORT_BYTES) {
      setState({ status: "error", message: `"${file.name}" is ${formatBytes(file.size)}. The maximum file size is ${formatBytes(MAX_IMPORT_BYTES)}.` });
      return;
    }
    if (ext !== ".csv") {
      setState({ status: "excel", file });
      return;
    }
    setState({ status: "reading", file });
    try {
      const table = parseCsv(await file.text());
      if (table.length < 2) {
        setState({ status: "error", message: "The CSV needs a header row and at least one data row." });
        return;
      }
      setState({ status: "csv", file, analysis: analyseCsv(table) });
    } catch {
      setState({ status: "error", message: "The file could not be read. Check that it is a valid UTF-8 CSV." });
    }
  }

  function reset() {
    setState({ status: "idle" });
    if (inputRef.current) inputRef.current.value = "";
  }

  function downloadTemplate() {
    const url = URL.createObjectURL(new Blob([TEMPLATE_CSV], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "customeriq-import-template.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Upload customer and order data</CardTitle>
            <CardDescription>
              CSV, XLSX, or XLS up to {formatBytes(MAX_IMPORT_BYTES)}. One row per order.
            </CardDescription>
          </div>
          <Button variant="secondary" onClick={downloadTemplate} className="mt-3 sm:mt-0">
            <Download className="h-4 w-4" aria-hidden="true" />
            CSV template
          </Button>
        </CardHeader>
        <CardContent>
          <label
            htmlFor="import-file"
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              const file = event.dataTransfer.files[0];
              if (file) void handleFile(file);
            }}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition focus-within:ring-2 focus-within:ring-teal-500/40",
              dragging ? "border-teal-500 bg-teal-50" : "border-slate-200 bg-slate-50 hover:border-teal-300",
            )}
          >
            <UploadCloud className="h-8 w-8 text-teal-600" aria-hidden="true" />
            <span className="mt-3 text-sm font-medium text-slate-900">
              Drag and drop a file, or <span className="text-teal-700 underline">browse</span>
            </span>
            <span className="mt-1 text-xs text-slate-500">
              Required columns: {REQUIRED_COLUMNS.join(", ")}
            </span>
            <input
              ref={inputRef}
              id="import-file"
              type="file"
              accept={ACCEPTED_EXTENSIONS.join(",")}
              className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleFile(file);
              }}
            />
          </label>
        </CardContent>
      </Card>

      <div aria-live="polite">
        {state.status === "idle" ? (
          <EmptyState
            icon={FileSpreadsheet}
            title="No file selected"
            description="Choose a file to validate its columns and preview the rows before importing."
          />
        ) : null}

        {state.status === "reading" ? (
          <Card className="flex items-center gap-3 p-5 text-sm text-slate-600">
            <Loader2 className="h-4 w-4 animate-spin text-teal-600" aria-hidden="true" />
            Reading {state.file.name}…
          </Card>
        ) : null}

        {state.status === "error" ? (
          <ErrorState
            title="This file can't be imported"
            description={state.message}
            action={<Button variant="secondary" onClick={reset}>Choose another file</Button>}
          />
        ) : null}

        {state.status === "excel" ? (
          <Card>
            <FileHeader file={state.file} onRemove={reset} />
            <CardContent>
              <p className="rounded-xl bg-sky-50 px-3 py-2 text-sm text-sky-900">
                Excel files are parsed by the import service on the server. Column validation and
                preview will be available once the import API is connected. To preview now, export
                the sheet as CSV.
              </p>
              <ImportActions />
            </CardContent>
          </Card>
        ) : null}

        {state.status === "csv" ? (
          <CsvResult file={state.file} analysis={state.analysis} onRemove={reset} />
        ) : null}
      </div>
    </div>
  );
}

function FileHeader({ file, onRemove }: { file: File; onRemove: () => void }) {
  return (
    <CardHeader className="flex-row items-center justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <div className="rounded-xl bg-teal-50 p-2 text-teal-700">
          <FileSpreadsheet className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <CardTitle className="truncate">{file.name}</CardTitle>
          <CardDescription>{formatBytes(file.size)}</CardDescription>
        </div>
      </div>
      <Button variant="ghost" onClick={onRemove} aria-label={`Remove ${file.name}`}>
        <X className="h-4 w-4" aria-hidden="true" />
      </Button>
    </CardHeader>
  );
}

function ImportActions({ disabled = false }: { disabled?: boolean }) {
  return (
    <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
      <Button disabled={disabled || !IMPORT_ENDPOINT_AVAILABLE} aria-describedby="import-status">
        <UploadCloud className="h-4 w-4" aria-hidden="true" />
        Import customers
      </Button>
      <p id="import-status" className="text-xs text-slate-500">
        {IMPORT_ENDPOINT_AVAILABLE
          ? "Data will be cleaned, de-duplicated, and scored after import."
          : "Import is unavailable until the backend import API is connected. No data has left your browser."}
      </p>
    </div>
  );
}

function CheckRow({ ok, label, detail }: { ok: boolean; label: string; detail?: string }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      {ok ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden="true" />
      ) : (
        <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" aria-hidden="true" />
      )}
      <span>
        <span className="sr-only">{ok ? "Passed: " : "Issue: "}</span>
        <span className="text-slate-800">{label}</span>
        {detail ? <span className="block text-xs text-slate-500">{detail}</span> : null}
      </span>
    </li>
  );
}

function CsvResult({
  file,
  analysis,
  onRemove,
}: {
  file: File;
  analysis: CsvAnalysis;
  onRemove: () => void;
}) {
  const { headers, rows, missingColumns } = analysis;
  const blocking = missingColumns.length > 0;
  const preview = rows.slice(0, PREVIEW_ROWS);

  return (
    <div className="space-y-6">
      <Card>
        <FileHeader file={file} onRemove={onRemove} />
        <CardContent>
          <div className="mb-4 flex flex-wrap gap-2">
            <Badge variant="info">{formatNumber(rows.length)} rows</Badge>
            <Badge variant="default">{headers.length} columns</Badge>
            <Badge variant={blocking ? "danger" : "success"}>
              {blocking ? "Fix required" : "Ready to import"}
            </Badge>
          </div>
          <ul className="space-y-2">
            <CheckRow
              ok={!blocking}
              label={blocking ? `Missing required columns: ${missingColumns.join(", ")}` : "All required columns present"}
              detail={`Recognised: ${analysis.recognisedColumns.join(", ") || "none"}`}
            />
            <CheckRow
              ok={analysis.emptyRequiredCells === 0}
              label={`${formatNumber(analysis.emptyRequiredCells)} empty values in required columns`}
              detail="Rows with missing values are handled during server-side cleaning."
            />
            <CheckRow
              ok={analysis.duplicateOrderIds === 0}
              label={`${formatNumber(analysis.duplicateOrderIds)} duplicate order IDs`}
              detail="Duplicates are removed before analysis."
            />
            <CheckRow
              ok={analysis.invalidOrderValues === 0}
              label={`${formatNumber(analysis.invalidOrderValues)} non-numeric order values`}
            />
          </ul>
          <ImportActions disabled={blocking} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Preview</CardTitle>
          <CardDescription>
            First {preview.length} of {formatNumber(rows.length)} rows, parsed locally in your browser.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <caption className="sr-only">Preview of uploaded rows</caption>
              <thead className="border-b border-slate-200 text-slate-500">
                <tr>
                  {headers.map((h, i) => (
                    <th
                      key={`${h}-${i}`}
                      scope="col"
                      className={cn(
                        "whitespace-nowrap px-3 py-2 font-medium",
                        (REQUIRED_COLUMNS as readonly string[]).includes(h) && "text-teal-700",
                      )}
                    >
                      {h || `column_${i + 1}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.map((row, r) => (
                  <tr key={r} className="border-b border-slate-100 last:border-0">
                    {headers.map((_, c) => (
                      <td key={c} className="max-w-[220px] truncate whitespace-nowrap px-3 py-2 text-slate-700">
                        {row[c] || <span className="text-slate-300">—</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}