import { CheckCircle2, Circle } from "lucide-react";
import { DataImporter } from "@/components/data-importer";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { OPTIONAL_COLUMNS, REQUIRED_COLUMNS } from "@/lib/api/data-import";

const sources = [
  { name: "CSV upload", status: "Preview available" },
  { name: "Excel (.xlsx, .xls)", status: "Needs import API" },
  { name: "Shopify", status: "Not connected" },
  { name: "WooCommerce", status: "Not connected" },
  { name: "CRM integrations", status: "Not connected" },
];

const pipeline = [
  "Validate file and columns",
  "Clean data and handle missing values",
  "Remove duplicate orders",
  "Engineer features (recency, frequency, monetary)",
  "Run segmentation, churn, CLV, and health models",
];

export default function ImportPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Import Customer Data"
        description="Upload customer and order history from a CSV or Excel export to power segmentation, churn, and CLV analysis."
      />
      <div className="grid gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <DataImporter />
        </div>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Expected columns</CardTitle>
              <CardDescription>Header names are case-insensitive.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">Required</p>
                <div className="flex flex-wrap gap-1.5">
                  {REQUIRED_COLUMNS.map((c) => (
                    <code key={c} className="rounded-md bg-teal-50 px-1.5 py-0.5 text-xs text-teal-800">{c}</code>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">Optional</p>
                <div className="flex flex-wrap gap-1.5">
                  {OPTIONAL_COLUMNS.map((c) => (
                    <code key={c} className="rounded-md bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">{c}</code>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Data sources</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="divide-y divide-slate-100 text-sm">
                {sources.map((s) => (
                  <li key={s.name} className="flex items-center justify-between gap-2 py-2 first:pt-0 last:pb-0">
                    <span className="text-slate-700">{s.name}</span>
                    <Badge variant={s.status === "Preview available" ? "success" : "default"}>{s.status}</Badge>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>After import</CardTitle>
              <CardDescription>Processing steps run by the backend.</CardDescription>
            </CardHeader>
            <CardContent>
              <ol className="space-y-2 text-sm text-slate-600">
                {pipeline.map((step, i) => (
                  <li key={step} className="flex items-start gap-2">
                    {i === 0 ? (
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden="true" />
                    ) : (
                      <Circle className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" aria-hidden="true" />
                    )}
                    {step}
                  </li>
                ))}
              </ol>
              <p className="mt-3 text-xs text-slate-500">Only step 1 runs today, in your browser.</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}