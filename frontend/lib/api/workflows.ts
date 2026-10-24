// Automation engine (browser side): /api/v1/workflows.

import { apiDelete, apiGet, apiPostJson, apiPutJson } from "@/lib/api/config";

export type Rule = { field: string; operator: string; value: string | number | boolean | string[] };
export type Conditions = { op?: "and" | "or"; rules?: Rule[] };
export type Action = { type: string; params: Record<string, string | number>; delayMinutes: number };
export type Definition = {
  name: string;
  description?: string | null;
  trigger: string;
  triggerConfig: Record<string, number>;
  conditions: Conditions;
  actions: Action[];
};
export type Workflow = Definition & { id: number; enabled: boolean; version: number; createdBy: string | null; runs: number; failedRuns: number };

export type Meta = {
  triggers: { id: string; label: string; carries: string[] }[];
  fields: { id: string; type: "number" | "text" | "list" | "bool"; needs: string; label: string; operators: string[] }[];
  operatorLabels: Record<string, string>;
  actions: { id: string; label: string; needs: string[] }[];
  orderStatuses: string[];
  messageEvents: string[];
  limits: { maxRules: number; maxActions: number; maxDelayMinutes: number };
};

export type TestStep = { index: number; type: string; delayMinutes: number; wouldDo: string };
export type TestResult = {
  matched: boolean;
  trace: { field: string; label: string; operator: string; value: unknown; actual: unknown; matched: boolean }[];
  facts: Record<string, unknown>;
  steps: TestStep[];
};
export type Job = { id: number; stepIndex: number; actionType: string; runAt: string; status: string; attempts: number; maxAttempts: number; lastError: string | null; result: Record<string, unknown> | null; finishedAt: string | null };
export type Run = { id: number; workflowId: number; workflowName: string; workflowVersion: number; eventKey: string; status: string; startedAt: string; finishedAt: string | null; context: Record<string, unknown>; jobs: Job[] };
export type FailedJob = Job & { runId: number; workflowName: string };
export type TaskRow = { id: number; kind: "task" | "notification"; title: string; detail: string | null; customerId: number | null; dueAt: string | null; done: boolean; createdAt: string };

const P = "/api/v1/workflows";
export const getMeta = () => apiGet<Meta>(`${P}/meta`);
export const listWorkflows = () => apiGet<Workflow[]>(P);
export const validateWorkflow = (d: Definition) => apiPostJson<{ valid: boolean; problems: string[] }>(`${P}/validate`, d);
export const createWorkflow = (d: Definition) => apiPostJson<Workflow>(P, d);
export const updateWorkflow = (id: number, d: Definition) => apiPutJson<Workflow>(`${P}/${id}`, d);
export const enableWorkflow = (id: number) => apiPostJson<Workflow>(`${P}/${id}/enable`, {});
export const disableWorkflow = (id: number) => apiPostJson<Workflow>(`${P}/${id}/disable`, {});
export const deleteWorkflow = (id: number) => apiDelete<void>(`${P}/${id}`);
export const testWorkflow = (definition: Definition, ids: { orderId?: number; customerId?: number; status?: string; text?: string }) => apiPostJson<TestResult>(`${P}/test`, { definition, ...ids });
export const listRuns = (status?: string) => apiGet<Omit<Run, "jobs">[]>(`${P}/runs/list${status ? `?status=${status}` : ""}`);
export const getRun = (id: number) => apiGet<Run>(`${P}/runs/${id}`);
export const cancelRun = (id: number) => apiPostJson<Run>(`${P}/runs/${id}/cancel`, {});
export const listFailedJobs = () => apiGet<FailedJob[]>(`${P}/jobs/failed`);
export const retryJob = (id: number) => apiPostJson<Job>(`${P}/jobs/${id}/retry`, {});
export const runDueJobs = () => apiPostJson<Record<string, number>>(`${P}/run-due`, {});
export const listTasks = (showDone = false) => apiGet<TaskRow[]>(`${P}/tasks/list${showDone ? "?showDone=true" : ""}`);
export const markTaskDone = (id: number) => apiPostJson<TaskRow>(`${P}/tasks/${id}/done`, {});

export const BLANK: Definition = { name: "", description: "", trigger: "order_created", triggerConfig: {}, conditions: { op: "and", rules: [] }, actions: [{ type: "notify", params: { title: "" }, delayMinutes: 0 }] };
