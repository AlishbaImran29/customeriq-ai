"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUp, CheckCircle2, FlaskConical, Loader2, Pause, Play, Plus, Save, Trash2, XCircle } from "lucide-react";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { API_MODE, ApiError } from "@/lib/api/config";
import { listOrders, type OrderRow } from "@/lib/api/messaging";
import {
  BLANK, createWorkflow, deleteWorkflow, disableWorkflow, enableWorkflow, getMeta, listWorkflows, testWorkflow, updateWorkflow, validateWorkflow,
  type Action, type Definition, type Meta, type Rule, type TestResult, type Workflow,
} from "@/lib/api/workflows";
import { fmt } from "@/lib/format";

const field = "flex flex-col gap-1 text-sm font-medium text-ink-2";

/**
 * Workflow builder: pick a trigger, add conditions, add actions with waits, check it, test it on a real order (nothing is sent or
 * changed), save, and switch it on. A workflow is data from a fixed list of choices: nothing typed here is ever run as code.
 */
export function WorkflowBuilder() {
  if (API_MODE !== "live") return <p className="text-sm text-muted">Workflows are saved in your database. Connect the backend to use them.</p>;
  return <BuilderContent />;
}

function BuilderContent() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [workflows, setWorkflows] = useState<Workflow[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState<{ id: number | null; draft: Definition } | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getMeta(), listWorkflows()])
      .then(([m, w]) => !cancelled && (setMeta(m), setWorkflows(w), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (failed) return <ErrorState title="Could not load the workflows" description="Please check your connection and reload the page." />;
  if (!meta || !workflows) return <Skeleton className="h-64 w-full" />;
  if (editing) return <Editor meta={meta} id={editing.id} initial={editing.draft} onDone={() => { setEditing(null); reload(); }} />;
  return (
    <div className="space-y-5">
      <Button onClick={() => setEditing({ id: null, draft: structuredClone(BLANK) })}><Plus className="h-4 w-4" aria-hidden="true" />New workflow</Button>
      {workflows.length === 0 ? <p className="text-sm text-muted">No workflows yet.</p> : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {workflows.map((w) => <Row key={w.id} meta={meta} w={w} onEdit={() => setEditing({ id: w.id, draft: w })} onChanged={reload} />)}
        </ul>
      )}
    </div>
  );
}

function Row({ meta, w, onEdit, onChanged }: { meta: Meta; w: Workflow; onEdit: () => void; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const trigger = meta.triggers.find((x) => x.id === w.trigger)?.label ?? w.trigger;

  async function toggle() {
    setError(null);
    try {
      await (w.enabled ? disableWorkflow(w.id) : enableWorkflow(w.id));
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    }
  }

  return (
    <li>
      <Card className="h-full">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">{w.name}
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${w.enabled ? "bg-success/15 text-success" : "bg-surface-3 text-ink-2"}`}>{w.enabled ? "On" : "Off"}</span>
          </CardTitle>
          <CardDescription>When: {trigger} · {fmt("{n} actions", { n: w.actions.length })} · v{w.version}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="text-xs text-muted">{fmt("{runs} runs, {failed} failed", { runs: w.runs, failed: w.failedRuns })}</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={onEdit}>Open</Button>
            <Button variant={w.enabled ? "ghost" : "primary"} onClick={toggle}>{w.enabled ? <Pause className="h-4 w-4" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}{w.enabled ? "Pause" : "Switch on"}</Button>
          </div>
          <div aria-live="polite">{error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}</div>
        </CardContent>
      </Card>
    </li>
  );
}

function Editor({ meta, id, initial, onDone }: { meta: Meta; id: number | null; initial: Definition; onDone: () => void }) {
  const [d, setD] = useState<Definition>(initial);
  const [problems, setProblems] = useState<string[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [orderId, setOrderId] = useState<string>("");
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  useEffect(() => {
    listOrders().then((r) => setOrders(r.slice(0, 30))).catch(() => undefined);
  }, []);

  const trigger = meta.triggers.find((x) => x.id === d.trigger);
  const carries = new Set(trigger?.carries ?? []);
  const fields = meta.fields.filter((f) => carries.has(f.needs));
  const actionTypes = meta.actions.filter((a) => a.needs.every((n) => carries.has(n)));
  const rules = d.conditions.rules ?? [];

  const setRules = (r: Rule[]) => setD({ ...d, conditions: { ...d.conditions, rules: r } });
  const setAction = (i: number, a: Action) => setD({ ...d, actions: d.actions.map((x, k) => (k === i ? a : x)) });
  const move = (i: number, by: number) => {
    const next = [...d.actions];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    setD({ ...d, actions: next });
  };

  function changeTrigger(value: string) {
    const nextCarries = new Set(meta.triggers.find((x) => x.id === value)?.carries ?? []);
    setD({
      ...d, trigger: value, triggerConfig: value === "customer_inactive" ? { days: 60 } : {},
      conditions: { ...d.conditions, rules: rules.filter((r) => nextCarries.has(meta.fields.find((f) => f.id === r.field)?.needs ?? "")) },
      actions: d.actions.filter((a) => (meta.actions.find((x) => x.id === a.type)?.needs ?? []).every((n) => nextCarries.has(n))),
    });
    setTestResult(null);
  }

  function addRule() {
    const f = fields[0];
    if (f) setRules([...rules, { field: f.id, operator: f.operators[0], value: f.type === "number" ? 0 : f.type === "bool" ? true : "" }]);
  }

  function changeField(i: number, fieldId: string) {
    const f = meta.fields.find((x) => x.id === fieldId)!;
    setRules(rules.map((r, k) => (k === i ? { field: fieldId, operator: f.operators[0], value: f.type === "number" ? 0 : f.type === "bool" ? true : "" } : r)));
  }

  function addAction() {
    const a = actionTypes[0];
    if (a) setD({ ...d, actions: [...d.actions, { type: a.id, params: defaultParams(a.id, meta), delayMinutes: 0 }] });
  }

  async function run<T>(name: string, work: () => Promise<T>): Promise<T | undefined> {
    setBusy(name);
    setNote(null);
    try {
      return await work();
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      if (e instanceof ApiError && Array.isArray((e.details as { problems?: string[] } | undefined)?.problems)) setProblems((e.details as { problems: string[] }).problems);
      return undefined;
    } finally {
      setBusy(null);
    }
  }

  async function check() {
    const r = await run("check", () => validateWorkflow(d));
    if (r) setProblems(r.valid ? [] : r.problems);
  }
  async function test() {
    const r = await run("test", () => testWorkflow(d, orderId ? { orderId: Number(orderId), customerId: undefined } : {}));
    if (r) setTestResult(r);
  }
  async function save() {
    const r = await run("save", () => (id ? updateWorkflow(id, d) : createWorkflow(d)));
    if (r) onDone();
  }
  async function remove() {
    if (!id || !window.confirm("Delete this workflow and its logs?")) return;
    const r = await run("delete", async () => { await deleteWorkflow(id); return true; });
    if (r) onDone();
  }

  return (
    <div className="space-y-5">
      <Button variant="ghost" onClick={onDone}>Back to workflows</Button>
      <Card>
        <CardHeader><CardTitle>{id ? "Edit workflow" : "New workflow"}</CardTitle></CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className={field}>Name<Input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} maxLength={120} /></label>
            <label className={field}>Description (optional)<Input value={d.description ?? ""} onChange={(e) => setD({ ...d, description: e.target.value })} maxLength={300} /></label>
          </div>

          <section aria-label="Trigger" className="space-y-2">
            <h3 className="text-sm font-semibold text-ink">1. When this happens</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <Select value={d.trigger} onChange={(e) => changeTrigger(e.target.value)} className="w-full" aria-label="Trigger">
                {meta.triggers.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
              </Select>
              {d.trigger === "customer_inactive" ? (
                <label className={field}>Days without an order<Input type="number" min={7} max={730} value={d.triggerConfig.days ?? 60} onChange={(e) => setD({ ...d, triggerConfig: { days: Number(e.target.value) } })} /></label>
              ) : null}
            </div>
          </section>

          <section aria-label="Conditions" className="space-y-2">
            <h3 className="text-sm font-semibold text-ink">2. Only if (optional)</h3>
            {rules.length > 1 ? (
              <Select value={d.conditions.op ?? "and"} onChange={(e) => setD({ ...d, conditions: { ...d.conditions, op: e.target.value as "and" | "or" } })} className="w-full sm:w-72" aria-label="Join conditions with">
                <option value="and">All of these are true</option>
                <option value="or">Any of these is true</option>
              </Select>
            ) : null}
            {rules.map((r, i) => <RuleRow key={i} meta={meta} fields={fields} rule={r} onField={(v) => changeField(i, v)} onChange={(x) => setRules(rules.map((y, k) => (k === i ? x : y)))} onRemove={() => setRules(rules.filter((_, k) => k !== i))} />)}
            {fields.length === 0 ? <p className="text-xs text-muted">This trigger has no facts to check.</p> : rules.length < meta.limits.maxRules ? <Button variant="secondary" onClick={addRule}><Plus className="h-4 w-4" aria-hidden="true" />Add a condition</Button> : null}
          </section>

          <section aria-label="Actions" className="space-y-2">
            <h3 className="text-sm font-semibold text-ink">3. Then do this</h3>
            {d.actions.map((a, i) => (
              <ActionRow key={i} meta={meta} types={actionTypes} action={a} index={i} last={i === d.actions.length - 1}
                onChange={(x) => setAction(i, x)} onRemove={() => setD({ ...d, actions: d.actions.filter((_, k) => k !== i) })} onMove={(by) => move(i, by)} />
            ))}
            {d.actions.length < meta.limits.maxActions ? <Button variant="secondary" onClick={addAction}><Plus className="h-4 w-4" aria-hidden="true" />Add an action</Button> : null}
          </section>

          <div className="flex flex-wrap items-center gap-3" aria-live="polite">
            <Button variant="secondary" onClick={check} disabled={busy !== null}>{busy === "check" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <CheckCircle2 className="h-4 w-4" aria-hidden="true" />}Check</Button>
            <Button onClick={save} disabled={busy !== null || !d.name.trim()}>{busy === "save" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}Save</Button>
            {id ? <Button variant="ghost" onClick={remove} disabled={busy !== null}><Trash2 className="h-4 w-4" aria-hidden="true" />Delete</Button> : null}
            {note ? <p role="alert" className="text-sm text-danger">{note}</p> : null}
          </div>
          {problems ? (problems.length === 0 ? <p className="text-sm text-success">This workflow is valid.</p> : <ul className="list-disc space-y-1 pl-5 text-sm text-danger">{problems.map((p, i) => <li key={i}>{p}</li>)}</ul>) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-accent" aria-hidden="true" />Test run</CardTitle>
          <CardDescription>Pretend the trigger just happened for a real order. Nothing is sent and nothing is changed: you only see what would happen.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {carries.has("order") ? (
            <label className={field}>Choose an order
              <Select value={orderId} onChange={(e) => setOrderId(e.target.value)} className="w-full sm:w-96">
                <option value="">No order</option>
                {orders.map((o) => <option key={o.id} value={o.id}>{o.orderNumber} · {o.customerName}</option>)}
              </Select>
            </label>
          ) : null}
          <Button variant="secondary" onClick={test} disabled={busy !== null}>{busy === "test" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FlaskConical className="h-4 w-4" aria-hidden="true" />}Run the test</Button>
          {testResult ? <TestView r={testResult} /> : null}
        </CardContent>
      </Card>
    </div>
  );
}

function defaultParams(type: string, meta: Meta): Record<string, string | number> {
  if (type === "send_message") return { channel: "whatsapp", event: meta.messageEvents[0] ?? "" };
  if (type === "add_tag" || type === "remove_tag") return { tag: "" };
  if (type === "update_order_status") return { status: meta.orderStatuses[0] };
  if (type === "call_webhook") return { url: "https://" };
  return { title: "" };
}

function RuleRow({ meta, fields, rule, onField, onChange, onRemove }: { meta: Meta; fields: Meta["fields"]; rule: Rule; onField: (v: string) => void; onChange: (r: Rule) => void; onRemove: () => void }) {
  const f = meta.fields.find((x) => x.id === rule.field);
  if (!f) return null;
  const value =
    f.type === "number" ? <Input type="number" value={Number(rule.value)} onChange={(e) => onChange({ ...rule, value: Number(e.target.value) })} aria-label="Value" />
    : f.type === "bool" ? (
      <Select value={String(rule.value)} onChange={(e) => onChange({ ...rule, value: e.target.value === "true" })} className="w-full" aria-label="Value"><option value="true">Yes</option><option value="false">No</option></Select>
    ) : rule.operator === "in" ? <Input value={Array.isArray(rule.value) ? rule.value.join(", ") : String(rule.value)} onChange={(e) => onChange({ ...rule, value: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} placeholder="words separated by commas" aria-label="Value" />
    : <Input value={String(rule.value)} onChange={(e) => onChange({ ...rule, value: e.target.value })} maxLength={200} aria-label="Value" />;
  return (
    <div className="grid gap-2 sm:grid-cols-[1.4fr_1fr_1.4fr_auto]">
      <Select value={rule.field} onChange={(e) => onField(e.target.value)} className="w-full" aria-label="Fact">{fields.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}</Select>
      <Select value={rule.operator} onChange={(e) => onChange({ ...rule, operator: e.target.value, value: e.target.value === "in" ? [] : f.type === "number" ? 0 : rule.value })} className="w-full" aria-label="Comparison">
        {f.operators.map((o) => <option key={o} value={o}>{(meta.operatorLabels[o] ?? o)}</option>)}
      </Select>
      {value}
      <Button variant="ghost" onClick={onRemove} aria-label="Remove this condition"><Trash2 className="h-4 w-4" aria-hidden="true" /></Button>
    </div>
  );
}

function ActionRow({ meta, types, action, index, last, onChange, onRemove, onMove }: { meta: Meta; types: Meta["actions"]; action: Action; index: number; last: boolean; onChange: (a: Action) => void; onRemove: () => void; onMove: (by: number) => void }) {
  const p = action.params;
  const setP = (key: string, value: string | number) => onChange({ ...action, params: { ...p, [key]: value } });
  return (
    <div className="space-y-2 rounded-xl border border-line bg-surface-2 p-3">
      <div className="grid gap-2 sm:grid-cols-[1.5fr_1fr_auto]">
        <Select value={action.type} onChange={(e) => onChange({ type: e.target.value, params: defaultParams(e.target.value, meta), delayMinutes: action.delayMinutes })} className="w-full" aria-label="Action">
          {types.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
        </Select>
        <label className="flex items-center gap-2 text-xs text-ink-2">Wait (minutes)
          <Input type="number" min={0} value={action.delayMinutes} onChange={(e) => onChange({ ...action, delayMinutes: Math.max(0, Math.floor(Number(e.target.value)) || 0) })} className="w-24" />
        </label>
        <div className="flex gap-1">
          <Button variant="ghost" disabled={index === 0} onClick={() => onMove(-1)} aria-label="Move up"><ArrowUp className="h-4 w-4" aria-hidden="true" /></Button>
          <Button variant="ghost" disabled={last} onClick={() => onMove(1)} aria-label="Move down"><ArrowDown className="h-4 w-4" aria-hidden="true" /></Button>
          <Button variant="ghost" onClick={onRemove} aria-label="Remove this action"><Trash2 className="h-4 w-4" aria-hidden="true" /></Button>
        </div>
      </div>
      {action.type === "send_message" ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <Select value={String(p.channel)} onChange={(e) => setP("channel", e.target.value)} className="w-full" aria-label="Channel"><option value="whatsapp">WhatsApp</option><option value="email">Email</option></Select>
          <Select value={String(p.event)} onChange={(e) => setP("event", e.target.value)} className="w-full" aria-label="Message">
            {meta.messageEvents.length === 0 ? <option value="">No templates yet</option> : null}
            {meta.messageEvents.map((e) => <option key={e} value={e}>{e}</option>)}
          </Select>
        </div>
      ) : null}
      {action.type === "add_tag" || action.type === "remove_tag" ? <Input value={String(p.tag ?? "")} onChange={(e) => setP("tag", e.target.value)} maxLength={30} placeholder="Tag" aria-label="Tag" /> : null}
      {action.type === "create_task" || action.type === "notify" ? <Input value={String(p.title ?? "")} onChange={(e) => setP("title", e.target.value)} maxLength={200} placeholder="Title" aria-label="Title" /> : null}
      {action.type === "update_order_status" ? <Select value={String(p.status)} onChange={(e) => setP("status", e.target.value)} className="w-full" aria-label="Status">{meta.orderStatuses.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}</Select> : null}
      {action.type === "call_webhook" ? <Input value={String(p.url ?? "")} onChange={(e) => setP("url", e.target.value)} maxLength={300} placeholder="https://" aria-label="Web address" /> : null}
    </div>
  );
}

function TestView({ r }: { r: TestResult }) {
  return (
    <div className="space-y-3 text-sm">
      <p className={r.matched ? "text-success" : "text-warning"}>{r.matched ? "The conditions hold: this workflow would run." : "The conditions do not hold: this workflow would not run."}</p>
      {r.trace.length > 0 ? (
        <ul className="space-y-1 text-xs text-ink-2">
          {r.trace.map((x, i) => <li key={i} className="flex items-center gap-1">{x.matched ? <CheckCircle2 className="h-3 w-3 text-success" aria-hidden="true" /> : <XCircle className="h-3 w-3 text-danger" aria-hidden="true" />}{x.label}: {x.actual === null || x.actual === undefined ? "not known" : String(x.actual)}</li>)}
        </ul>
      ) : null}
      {r.steps.length > 0 ? (
        <ol className="list-decimal space-y-1 pl-5 text-ink-2">
          {r.steps.map((s) => <li key={s.index}>{s.delayMinutes > 0 ? `[+${s.delayMinutes} min] ` : ""}{s.wouldDo}</li>)}
        </ol>
      ) : null}
    </div>
  );
}
