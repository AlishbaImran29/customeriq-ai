"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CircleCheck, Loader2, Pencil, Plus, Save, ShieldCheck, ShieldOff, Sparkles, Trash2 } from "lucide-react";
import { MessengerGate, areaClass, fieldClass } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import {
  approveTemplate, createTemplate, deleteTemplate, editTemplate, listTemplates, listVariables, previewTemplate, seedTemplates, unapproveTemplate,
  type Category, type Channel, type Lang, type MetaStatus, type Preview, type Template, type Variable,
} from "@/lib/api/messaging";
import { useLanguage } from "@/lib/i18n";
import { eventLabel } from "@/lib/messenger-text";

const META_LABEL: Record<MetaStatus, string> = { not_submitted: "Not sent to Meta", pending: "Waiting for Meta", approved: "Approved by Meta", rejected: "Rejected by Meta" };

/**
 * The wording of every message, in Urdu and English. A template is only used after YOU approve it, and changing its words
 * withdraws the approval. For WhatsApp, Meta must approve the same text too (the preview shows it in Meta's {{1}} form).
 */
export function MessengerTemplatesBoard() {
  return (
    <MessengerGate>
      <TemplatesContent />
    </MessengerGate>
  );
}

type Draft = { id: number | null; name: string; channel: Channel; category: Category; language: Lang; event: string; subject: string; body: string; metaName: string; metaStatus: MetaStatus };
const blank: Draft = { id: null, name: "", channel: "whatsapp", category: "utility", language: "en", event: "", subject: "", body: "", metaName: "", metaStatus: "not_submitted" };

function TemplatesContent() {
  const { t, tf } = useLanguage();
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [variables, setVariables] = useState<Variable[]>([]);
  const [failed, setFailed] = useState(false);
  const [filter, setFilter] = useState<"all" | Channel>("all");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    listTemplates().then((r) => (setTemplates(r), setFailed(false))).catch(() => setFailed(true));
  }, []);
  useEffect(() => {
    load();
    listVariables().then(setVariables).catch(() => undefined);
  }, [load]);

  function problem(e: unknown) {
    setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
  }

  async function seed(groups: ("orders" | "followups" | "journeys" | "carts")[]) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const { added } = await seedTemplates(groups);
      setMessage(tf("{count} templates added. Read each one and approve it before it can be used.", { count: added }));
      load();
    } catch (e) {
      problem(e);
    } finally {
      setBusy(false);
    }
  }

  async function act(run: () => Promise<unknown>) {
    setError(null);
    try {
      await run();
      load();
    } catch (e) {
      problem(e);
    }
  }

  if (failed) return <ErrorState title={t("Could not load the templates")} description={t("Please check your connection and reload the page.")} />;
  if (!templates) return <Skeleton className="h-64 w-full" />;
  const shown = templates.filter((x) => filter === "all" || x.channel === filter);

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("Start from ready-made templates")}</CardTitle>
          <CardDescription>{t("Urdu and English texts for order updates, unboxing and reviews, and for the automatic journeys. None is approved until you approve it.")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={busy} onClick={() => seed(["orders"])}><Sparkles className="h-4 w-4" aria-hidden="true" />{t("Add order update templates")}</Button>
          <Button variant="secondary" disabled={busy} onClick={() => seed(["followups"])}><Sparkles className="h-4 w-4" aria-hidden="true" />{t("Add unboxing and review templates")}</Button>
          <Button variant="secondary" disabled={busy} onClick={() => seed(["carts"])}><Sparkles className="h-4 w-4" aria-hidden="true" />{t("Add cart reminder templates")}</Button>
          <Button variant="secondary" disabled={busy} onClick={() => seed(["journeys"])}><Sparkles className="h-4 w-4" aria-hidden="true" />{t("Add journey templates")}</Button>
          <Button onClick={() => setDraft({ ...blank })}><Plus className="h-4 w-4" aria-hidden="true" />{t("New template")}</Button>
        </CardContent>
      </Card>

      <div aria-live="polite" className="space-y-1">
        {message ? <p className="text-sm text-success">{message}</p> : null}
        {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
      </div>

      {draft ? (
        <Editor
          key={draft.id ?? "new"} initial={draft} variables={variables} onClose={() => setDraft(null)}
          onSaved={() => { setDraft(null); load(); }}
        />
      ) : null}

      <FilterPills label={t("Filter by channel")} value={filter} onChange={setFilter} options={[{ value: "all" as const, label: t("All"), count: templates.length }, { value: "whatsapp" as const, label: "WhatsApp" }, { value: "email" as const, label: t("Email") }]} />

      {shown.length === 0 ? <p className="text-sm text-muted">{t("No templates yet.")}</p> : (
        <ul className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {shown.map((x) => (
            <li key={x.id}>
              <Card className="h-full">
                <CardContent className="space-y-3 pt-5 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-medium text-ink">{x.event ? t(eventLabel(x.event)) : x.name}</p>
                      <p className="text-xs text-muted">{x.name} · {x.channel === "whatsapp" ? "WhatsApp" : t("Email")} · {x.language === "ur" ? "اردو" : "English"} · {x.category === "utility" ? t("Order update") : t("Marketing")}</p>
                    </div>
                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${x.approvedBySeller ? "bg-success/10 text-success" : "bg-warning/10 text-warning"}`}>
                      {x.approvedBySeller ? <ShieldCheck className="h-3 w-3" aria-hidden="true" /> : <ShieldOff className="h-3 w-3" aria-hidden="true" />}
                      {x.approvedBySeller ? t("Approved by you") : t("Not approved")}
                    </span>
                  </div>
                  {x.subject ? <p className="text-xs text-ink-2"><strong>{t("Subject")}:</strong> {x.subject}</p> : null}
                  <p className="whitespace-pre-wrap rounded-xl border border-line bg-surface-2 p-3 text-ink-2" dir="auto">{x.body}</p>
                  {x.channel === "whatsapp" ? (
                    <p className="text-xs text-muted">{t("Meta")}: {t(META_LABEL[x.metaApprovalStatus])}{x.metaTemplateName ? ` (${x.metaTemplateName})` : ""}</p>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    {x.approvedBySeller ? (
                      <Button variant="secondary" onClick={() => act(() => unapproveTemplate(x.id))}><ShieldOff className="h-4 w-4" aria-hidden="true" />{t("Take out of use")}</Button>
                    ) : (
                      <Button onClick={() => act(() => approveTemplate(x.id))}><CircleCheck className="h-4 w-4" aria-hidden="true" />{t("Approve")}</Button>
                    )}
                    <Button variant="ghost" onClick={() => setDraft({ id: x.id, name: x.name, channel: x.channel, category: x.category, language: x.language, event: x.event ?? "", subject: x.subject ?? "", body: x.body, metaName: x.metaTemplateName ?? "", metaStatus: x.metaApprovalStatus })} aria-label={`${t("Edit")} ${x.name}`}><Pencil className="h-4 w-4" aria-hidden="true" />{t("Edit")}</Button>
                    <Button variant="ghost" onClick={() => act(() => deleteTemplate(x.id))} aria-label={`${t("Delete")} ${x.name}`}><Trash2 className="h-4 w-4" aria-hidden="true" /></Button>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Editor({ initial, variables, onClose, onSaved }: { initial: Draft; variables: Variable[]; onClose: () => void; onSaved: () => void }) {
  const { t } = useLanguage();
  const [d, setD] = useState<Draft>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const editing = d.id !== null;
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setD((old) => ({ ...old, [key]: value }));

  function insert(name: string) {
    const el = area.current;
    const token = `{{${name}}}`;
    if (!el) return set("body", d.body + token);
    const start = el.selectionStart ?? d.body.length;
    const end = el.selectionEnd ?? start;
    set("body", d.body.slice(0, start) + token + d.body.slice(end));
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + token.length, start + token.length);
    });
  }

  async function showPreview() {
    setError(null);
    try {
      setPreview(await previewTemplate({ body: d.body, subject: d.channel === "email" ? d.subject : undefined, language: d.language }));
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    }
  }

  async function save() {
    setError(null);
    setBusy(true);
    try {
      if (editing) {
        await editTemplate(d.id!, { name: d.name, category: d.category, event: d.event, subject: d.channel === "email" ? d.subject : undefined, body: d.body, metaTemplateName: d.metaName, metaApprovalStatus: d.metaStatus });
      } else {
        await createTemplate({ name: d.name, channel: d.channel, category: d.category, language: d.language, event: d.event || undefined, subject: d.channel === "email" ? d.subject : undefined, body: d.body, metaTemplateName: d.metaName || undefined });
      }
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{editing ? t("Edit template") : t("New template")}</CardTitle>
        <CardDescription>{editing ? t("Changing the words withdraws your approval (and Meta's): approve again after editing.") : t("Write the message. Use the {{variables}} below, they are filled in for each customer.")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className={fieldClass}>{t("Name")}<Input value={d.name} onChange={(e) => set("name", e.target.value)} maxLength={80} /></label>
          <label className={fieldClass}>{t("Channel")}
            <Select value={d.channel} disabled={editing} onChange={(e) => set("channel", e.target.value as Channel)} className="w-full"><option value="whatsapp">WhatsApp</option><option value="email">{t("Email")}</option></Select>
          </label>
          <label className={fieldClass}>{t("Language")}
            <Select value={d.language} disabled={editing} onChange={(e) => set("language", e.target.value as Lang)} className="w-full"><option value="en">English</option><option value="ur">اردو</option></Select>
          </label>
          <label className={fieldClass}>{t("Kind")}
            <Select value={d.category} onChange={(e) => set("category", e.target.value as Category)} className="w-full"><option value="utility">{t("Order update")}</option><option value="marketing">{t("Marketing")}</option></Select>
          </label>
        </div>
        <label className={`${fieldClass} block`}>{t("Event (which automatic message this is, optional)")}<Input value={d.event} onChange={(e) => set("event", e.target.value)} maxLength={40} placeholder="order_dispatched" /></label>
        {d.channel === "email" ? <label className={`${fieldClass} block`}>{t("Subject")}<Input value={d.subject} onChange={(e) => set("subject", e.target.value)} maxLength={200} dir="auto" /></label> : null}
        <label className={`${fieldClass} block`}>{t("Message")}<textarea ref={area} className={areaClass} rows={6} value={d.body} onChange={(e) => set("body", e.target.value)} maxLength={2000} dir="auto" /></label>
        <div>
          <p className="text-xs font-medium text-muted">{t("Click a variable to put it in the message")}</p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {variables.map((v) => (
              <li key={v.name}>
                <button type="button" onClick={() => insert(v.name)} title={v.description}
                  className="rounded-full border border-line bg-surface-2 px-2.5 py-1 text-xs text-ink-2 hover:border-accent/40 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40">
                  {`{{${v.name}}}`}{v.optional ? " ?" : ""}
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-muted">{t("A variable marked ? may be empty (it is left out). Any other must have a value or the message is not sent.")}</p>
        </div>
        {d.channel === "whatsapp" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className={fieldClass}>{t("Template name in Meta (optional)")}<Input value={d.metaName} onChange={(e) => set("metaName", e.target.value)} maxLength={100} /></label>
            <label className={fieldClass}>{t("What Meta said")}
              <Select value={d.metaStatus} onChange={(e) => set("metaStatus", e.target.value as MetaStatus)} className="w-full" disabled={!editing}>
                {(Object.keys(META_LABEL) as MetaStatus[]).map((m) => <option key={m} value={m}>{t(META_LABEL[m])}</option>)}
              </Select>
            </label>
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-2" aria-live="polite">
          <Button onClick={save} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}{t("Save template")}</Button>
          <Button variant="secondary" onClick={showPreview}>{t("Preview")}</Button>
          <Button variant="ghost" onClick={onClose}>{t("Cancel")}</Button>
          {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
        </div>
        {preview ? (
          <div className="space-y-2 rounded-xl border border-line bg-surface-2 p-3 text-sm">
            <p className="text-xs font-medium text-muted">{t("Example values, not a real customer")}</p>
            {preview.error ? <p role="alert" className="text-danger">{preview.error}</p> : (
              <>
                {preview.subject ? <p className="text-ink-2"><strong>{t("Subject")}:</strong> {preview.subject}</p> : null}
                <p className="whitespace-pre-wrap text-ink" dir="auto">{preview.text}</p>
                {d.channel === "whatsapp" ? (
                  <div className="border-t border-line pt-2 text-xs text-muted">
                    <p>{t("The same text as Meta wants it (create this in WhatsApp Manager):")}</p>
                    <p className="mt-1 whitespace-pre-wrap font-mono text-ink-2" dir="auto">{preview.metaBody}</p>
                    <p className="mt-1">{preview.metaVariables.map((v, i) => `{{${i + 1}}} = ${v}`).join(", ")}</p>
                  </div>
                ) : null}
              </>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
