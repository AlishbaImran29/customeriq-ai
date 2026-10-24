// Launch Studio service (browser side): launch projects, Google Trends files, own-product growth, AI ideas.

import { API_MODE, apiDelete, apiGet, apiPatchJson, apiPostForm, apiPostJson } from "@/lib/api/config";

export const LAUNCH_AVAILABLE = API_MODE === "live";

/** Must match MAX_TREND_FILE in backend/app/api/v1/launch.py. */
export const MAX_TREND_BYTES = 2 * 1024 * 1024;

export const STATUSES = ["idea", "sourcing", "ready", "launched", "dropped"] as const;
export type Status = (typeof STATUSES)[number];

export type Project = {
  id: number;
  productName: string;
  category: string | null;
  status: Status;
  notes: string | null;
  launchedOn: string | null;
  createdAt: string;
};

export type TrendLabel = "rising" | "stable" | "falling";

export type Trend = {
  id: number;
  launchProjectId: number | null;
  keyword: string;
  region: string | null;
  granularity: string | null;
  points: { date: string; value: number }[];
  related: { query: string; value: string; kind: "top" | "rising" }[];
  /** null = "Not enough data yet". */
  label: TrendLabel | null;
  /** Average of the last 4 weeks divided by the average of the 8 weeks before. */
  ratio: number | null;
  createdAt: string;
};

export type GrowthRow = { product: string; last: number; before: number; growth: number | null };

export type Growth = {
  days: number;
  /** "units" (product sales table), "orders" (product names on orders) or "" (no data). */
  metric: string;
  source: string;
  periodEnd: string | null;
  rows: GrowthRow[];
  tooSmall: number;
  minGroupCount: number;
  reason: "no_data" | "not_enough_history" | null;
};

export type Ideas = {
  label: "AI suggestion";
  ideas: { name: string; reason: string }[];
  /** true = the saved answer was used and nothing was paid for. */
  cached: boolean;
  model: string | null;
};

export const listProjects = () => apiGet<Project[]>("/api/v1/launch/projects");
export const createProject = (body: { productName: string; category?: string; notes?: string }) =>
  apiPostJson<Project>("/api/v1/launch/projects", body);
export const updateProject = (id: number, patch: Partial<Pick<Project, "productName" | "category" | "notes" | "status">>) =>
  apiPatchJson<Project>(`/api/v1/launch/projects/${id}`, patch);
export const deleteProject = (id: number) => apiDelete<void>(`/api/v1/launch/projects/${id}`);

export function uploadTrend(file: File, projectId?: number): Promise<Trend[]> {
  const form = new FormData();
  form.append("file", file);
  if (projectId) form.append("launch_project_id", String(projectId));
  return apiPostForm<Trend[]>("/api/v1/launch/trends/upload", form);
}
export const listTrends = () => apiGet<Trend[]>("/api/v1/launch/trends");
export const deleteTrend = (id: number) => apiDelete<void>(`/api/v1/launch/trends/${id}`);

export const getGrowth = (days: 30 | 90) => apiGet<Growth>(`/api/v1/launch/growth?days=${days}`);

export const askForIdeas = (force: boolean) => apiPostJson<Ideas>("/api/v1/launch/ideas", { force });
