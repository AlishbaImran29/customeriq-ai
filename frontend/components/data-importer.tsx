"use client";

import { useRef, useState } from "react";
import {
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Loader2,
  RotateCcw,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";
import { EmptyState, ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api/config";
import {
  ACCEPTED_EXTENSIONS,
  IMPORT_ENDPOINT_AVAILABLE,
  MAX_IMPORT_BYTES,
  REQUIRED_COLUMNS,
  TEMPLATE_CSV,
  analyseCsv,
  parseCsv,
  uploadImport,
  type CsvAnalysis,
  type ImportResult,
} from "@/lib/api/data-import";
import { cn, formatNumber } from "@/lib/utils";

type ImportState =
  | { status: "idle" }
  | { status: "reading"; file: File }
  | { status: "error"; message: string }
  | { status: "csv"; file: File; analysis: CsvAnalysis }
  | { status: "excel"; file: File };

type UploadState =
  | { status: "idle" }
  | { status: "uploading" }
  | { status: "done"; result: ImportResult }
  | { status: "failed"; message: string; hint?: string };

const PREVIEW_ROWS = 8;
const MAX_LISTED_ERRORS = 50;

function extensionOf(name: string) {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function describeUploadError(error: unknown): { message: string; hint?: string } {
  if (error instanceof ApiError) {
    const missing = (error.details as { missingColumns?: string[] } | undefined)?.missingColumns;
    if (missing?.length) {
      return {
        message: error.message,
        hint: "Add the missing columns to the header row and upload again. Nothing was saved.",
      };
    }
    if (error.code === "network_error") {
      return { message: error.message, hint: "Start the backend (see backend/README.md) and try again." };
    }
    if (error.status === 503) {
      return { message: error.message, hint: "The server could not reach its database. Nothing was saved." };
    }
    return { message: error.message };
  }
  return { message: "The upload failed for an unknown reason. Check the import history before retrying." };
}

export function DataImporter() {
  const [state, setState] = useState<ImportState>({ status: "idle" });
  const [upload, setUpload] = useState<UploadState>({ status: "idle" });
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setUpload({ status: "idle" });
    const ext = extensionOf(file.name);
    if (ext === ".xls") {
      setState({
        status: "error",
        message: `"${file.name}" is an old Excel .xls file. In Excel choose File → Save As → Excel Workbook (.xlsx), or export as CSV.`,
      });
      return;
    }
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
    setUpload({ status: "idle" });
    if (inputRef.current) inputRef.current.value = "";
  }

  async function startUpload(file: File) {
    setUpload({ status: "uploading" });
    try {
      setUpload({ status: "done", result: await uploadImport(file) });
    } catch (error) {
      setUpload({ status: "failed", ...describeUploadError(error) });
    }
  }

  function downloadTemplate() {
    const url = URL.createObjectURL(new Blob([TEMPLATE_CSV], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "customeriq-import-template.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  const selectedFile = state.status === "csv" || state.status === "excel" ? state.file : null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Upload customer and order data</CardTitle>
            <CardDescription>
              CSV or XLSX up to {formatBytes(MAX_IMPORT_BYTES)}. One row per order.
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

      <div aria-live="polite" className="space-y-6">
        {state.status === "idle" ? (
          <EmptyState
            icon={FileSpreadsheet}
            title="No file selected"
            description="Choose a file to check its columns and preview the rows before importing."
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

        {upload.status === "done" ? <ImportResultCard result={upload.result} onReset={reset} /> : null}

        {upload.status === "failed" ? (
          <ErrorState
            title="Import failed"
            description={upload.hint ? `${upload.message} ${upload.hint}` : upload.message}
            action={
              selectedFile ? (
                <Button variant="secondary" onClick={() => startUpload(selectedFile)}>
                  <RotateCcw className="h-4 w-4" aria-hidden="true" />
                  Try again
                </Button>
              ) : null
            }
          />
        ) : null}

        {state.status === "excel" ? (
          <Card>
            <FileHeader file={state.file} onRemove={reset} />
            <CardContent>
              <p className="rounded-xl bg-sky-50 px-3 py-2 text-sm text-sky-900">
                Excel files are read and checked on the server when you import, so there is no
                preview here. The first sheet is used. To preview first, export the sheet as CSV.
              </p>
              <ImportActions upload={upload} onImport={() => startUpload(state.file)} />
            </CardContent>
          </Card>
        ) : null}

        {state.status === "csv" ? (
          <CsvResult
            file={state.file}
            analysis={state.analysis}
            onRemove={reset}
            actions={
              <ImportActions
                upload={upload}
                disabled={state.analysis.missingColumns.length > 0}
                onImport={() => startUpload(state.file)}
              />
            }
          />
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

function ImportActions({
  upload,
  onImport,
  disabled = false,
}: {
  upload: UploadState;
  onImport: () => void;
  disabled?: boolean;
}) {
  if (upload.status === "done") return null;
  const uploading = upload.status === "uploading";
  return (
    <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
      <Button
        disabled={disabled || uploading || !IMPORT_ENDPOINT_AVAILABLE}
        aria-describedby="import-status"
        onClick={onImport}
      >
        {uploading ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <UploadCloud className="h-4 w-4" aria-hidden="true" />
        )}
        {uploading ? "Importing…" : "Import customers"}
      </Button>
      <p id="import-status" className="text-xs text-slate-500">
        {!IMPORT_ENDPOINT_AVAILABLE
          ? "Demo mode: no backend is configured (NEXT_PUBLIC_API_BASE_URL), so import is disabled. No data has left your browser."
          : uploading
            ? "Uploading and checking every row on the server…"
            : "The server checks every row, saves valid rows, updates existing order IDs, and lists rejected rows."}
      </p>
    </div>
  );
}

function ImportResultCard({ result, onReset }: { result: ImportResult; onReset: () => void }) {
  const failed = result.status === "failed";
  const saved = result.rowsImported + result.rowsUpdated;
  const listed = result.errors.slice(0, MAX_LISTED_ERRORS);
  const hiddenErrors = result.errorCount - listed.length;
  const stats = [
    { label: "Rows received", value: result.rowsReceived },
    { label: "New orders", value: result.rowsImported },
    { label: "Updated orders", value: result.rowsUpdated },
    { label: "Rejected rows", value: result.rowsRejected },
  ];

  return (
    <Card>
      <CardHeader className="sm:flex-row sm:items-start sm:justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            {failed || saved === 0 ? (
              <XCircle className="h-4 w-4 text-rose-600" aria-hidden="true" />
            ) : (
              <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
            )}
            {failed ? "Import failed" : saved > 0 ? "Import complete" : "Import finished — no rows saved"}
          </CardTitle>
          <CardDescription>
            {result.filename} · processed on the server.
            {result.rowsRejected > 0
              ? " Fix the rejected rows and upload the file again — orders already saved will be updated, not duplicated."
              : ""}
          </CardDescription>
        </div>
        <Button variant="secondary" onClick={onReset} className="mt-3 sm:mt-0">
          Import another file
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stats.map((stat) => (
            <div key={stat.label} className="rounded-xl border border-slate-100 p-3">
              <dt className="text-xs text-slate-500">{stat.label}</dt>
              <dd className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{formatNumber(stat.value)}</dd>
            </div>
          ))}
        </dl>
        {listed.length > 0 ? (
          <div>
            <p className="mb-2 text-sm font-medium text-slate-900">
              Problems found ({formatNumber(result.errorCount)})
            </p>
            <div className="max-h-80 overflow-auto rounded-xl border border-slate-100">
              <table className="w-full text-left text-xs">
                <caption className="sr-only">Rows rejected by the server and why</caption>
                <thead className="sticky top-0 bg-slate-50 text-slate-500">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-medium">Row</th>
                    <th scope="col" className="px-3 py-2 font-medium">Column</th>
                    <th scope="col" className="px-3 py-2 font-medium">Problem</th>
                  </tr>
                </thead>
                <tbody>
                  {listed.map((error, i) => (
                    <tr key={`${error.row}-${error.column}-${i}`} className="border-t border-slate-100">
                      <td className="px-3 py-2 tabular-nums text-slate-700">{error.row ?? "—"}</td>
                      <td className="px-3 py-2">
                        <code className="text-slate-700">{error.column ?? "—"}</code>
                      </td>
                      <td className="px-3 py-2 text-slate-600">{error.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {hiddenErrors > 0 ? (
              <p className="mt-2 text-xs text-slate-500">
                {formatNumber(hiddenErrors)} more problem{hiddenErrors === 1 ? "" : "s"} not shown.
                Fix the ones above and upload again to see the rest.
              </p>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
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
  actions,
}: {
  file: File;
  analysis: CsvAnalysis;
  onRemove: () => void;
  actions: React.ReactNode;
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
              detail="Rows with missing required values are rejected by the server and listed."
            />
            <CheckRow
              ok={analysis.duplicateOrderIds === 0}
              label={`${formatNumber(analysis.duplicateOrderIds)} duplicate order IDs`}
              detail="Only the first row for each order ID in a file is imported."
            />
            <CheckRow
              ok={analysis.invalidOrderValues === 0}
              label={`${formatNumber(analysis.invalidOrderValues)} non-numeric order values`}
            />
          </ul>
          <p className="mt-3 text-xs text-slate-500">
            Quick browser check only — the server re-checks every row when you import.
          </p>
          {actions}
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
