import Link from "next/link";
import { CheckCircle2, Circle, Download, MessagesSquare } from "lucide-react";
import { DataImporter } from "@/components/data-importer";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { API_MODE } from "@/lib/api/config";
import { OPTIONAL_COLUMNS, REQUIRED_COLUMNS } from "@/lib/api/data-import";
import { T } from "@/components/t";

const live = API_MODE === "live";

const sources = [
  { name: "CSV upload", status: live ? "Connected" : "Preview only (demo)", ok: live },
  { name: "Excel (.xlsx)", status: live ? "Connected" : "Needs backend", ok: live },
  { name: "Shopify orders export (CSV)", status: live ? "Supported" : "Needs backend", ok: live },
  { name: "WhatsApp chat export (.txt)", status: live ? "Supported" : "Needs backend", ok: live },
  { name: "Shopify API sync", status: "Not built yet", ok: false },
  { name: "WooCommerce", status: "Not built yet", ok: false },
  { name: "CRM integrations", status: "Not built yet", ok: false },
];

// `done` marks the steps the backend actually performs today.
const pipeline = [
  { step: "Validate file, columns, and every row", done: live },
  { step: "Clean values; reject rows with missing required data", done: live },
  { step: "Skip duplicate order IDs in a file; update existing orders", done: live },
  { step: "Engineer features (recency, frequency, monetary)", done: false },
  { step: "Segmentation and health scores calculated from your data", done: live },
  { step: "Churn, CLV, and forecast models retrain automatically (only shown if accurate enough)", done: live },
];

export default function ImportPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Import Customer Data"
        description="Upload customer and order history from a CSV or Excel export to power segmentation, churn, and CLV analysis."
        actions={
          <Link
            href="/import/whatsapp"
            className="inline-flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3.5 py-2 text-sm font-medium text-ink-2 transition hover:bg-surface-3 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
          >
            <MessagesSquare className="h-4 w-4" aria-hidden="true" />
            Import a WhatsApp chat
          </Link>
        }
      />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <DataImporter />
        </div>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle><T>Keep your orders in a sheet?</T></CardTitle>
              <CardDescription>
                <T>Download the template, fill in one order per row, and upload it here. Upload it again as it grows: orders already imported are not added twice.</T>
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <a
                href="/seller_orders_template.xlsx"
                download
                className="inline-flex items-center gap-2 rounded-xl bg-accent px-3.5 py-2 text-sm font-medium text-accent-ink hover:bg-accent-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
              >
                <Download className="h-4 w-4" aria-hidden="true" />
                <T>Excel template</T>
              </a>
              <a
                href="/seller_orders_template.csv"
                download
                className="inline-flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3.5 py-2 text-sm font-medium text-ink-2 hover:bg-surface-3 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
              >
                <Download className="h-4 w-4" aria-hidden="true" />
                <T>CSV template</T>
              </a>
              <p className="w-full text-xs text-muted">
                <T>In Google Sheets: File, Import, Upload the CSV template. When you are done, File, Download, CSV.</T>
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Expected columns</CardTitle>
              <CardDescription>Header names are case-insensitive.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted">Required</p>
                <div className="flex flex-wrap gap-1.5">
                  {REQUIRED_COLUMNS.map((c) => (
                    <code key={c} className="rounded-md bg-accent/10 px-1.5 py-0.5 text-xs text-accent">{c}</code>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted">Optional</p>
                <div className="flex flex-wrap gap-1.5">
                  {OPTIONAL_COLUMNS.map((c) => (
                    <code key={c} className="rounded-md bg-surface-3 px-1.5 py-0.5 text-xs text-ink-2">{c}</code>
                  ))}
                </div>
              </div>
              <ul className="space-y-1 text-xs text-muted">
                <li><code>order_date</code>: DD/MM/YYYY or YYYY-MM-DD (or an Excel date cell).</li>
                <li><code>order_value</code> (or <code>amount</code>): a number such as 142.50, no currency symbol.</li>
                <li><code>order_id</code> is optional: without it, one is made from the order itself.</li>
                <li>Each row needs a <code>customer_id</code>, <code>email</code> or <code>phone</code>.</li>
                <li>
                  <code>engagement</code>: optional 0–100 score. Leave it blank when unknown; blank is
                  never treated as 0.
                </li>
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Data sources</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="divide-y divide-line/60 text-sm">
                {sources.map((s) => (
                  <li key={s.name} className="flex items-center justify-between gap-2 py-2 first:pt-0 last:pb-0">
                    <span className="text-ink-2">{s.name}</span>
                    <Badge variant={s.ok ? "success" : "default"}>{s.status}</Badge>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>After import</CardTitle>
              <CardDescription>Processing steps run by the backend.</CardDescription>
              <div>
                <Badge variant={live ? "success" : "warning"}>
                  {live ? "Live API connected" : "Demo mode — no backend configured"}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <ol className="space-y-2 text-sm text-ink-2">
                {pipeline.map(({ step, done }) => (
                  <li key={step} className="flex items-start gap-2">
                    <span className="sr-only">{done ? "Available: " : "Not available yet: "}</span>
                    {done ? (
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />
                    ) : (
                      <Circle className="mt-0.5 h-4 w-4 shrink-0 text-faint" aria-hidden="true" />
                    )}
                    {step}
                  </li>
                ))}
              </ol>
              <p className="mt-3 text-xs text-muted">
                {live
                  ? "Steps 1–3 run on the server today. Analytics and models come in later phases."
                  : "In demo mode nothing is uploaded; CSVs are only previewed in your browser."}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}