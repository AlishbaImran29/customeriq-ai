"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, Loader2, Pencil, RefreshCw, Save, Sparkles, Trash2 } from "lucide-react";
import { LaunchStepFrame } from "@/components/launch-step-frame";
import { PostImageMaker } from "@/components/post-image-maker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input } from "@/components/ui/input";
import {
  editCreative, generateCreatives, listCreatives, regenerateCreative, removeCreative, saveCreative,
  type Angle, type Brief, type CreativeKind, type Creatives, type Language, type SavedCreative,
} from "@/lib/api/launch-steps";
import { ApiError } from "@/lib/api/config";
import type { Project } from "@/lib/api/launch";
import { adAsText, instagramAsText, parseHashtags } from "@/lib/launch-links";
import { fmt } from "@/lib/format";

const field = "space-y-1 text-xs font-medium text-muted";
const areaClass =
  "min-h-24 w-full rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-faint outline-none transition focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/30";

const ANGLE_LABEL: Record<Angle, string> = {
  price: "Price", quality: "Quality", urgency: "Urgency", social_proof: "Social proof", cod_trust: "Cash on delivery trust",
};
const TONES = ["Friendly", "Professional", "Exciting", "Calm"] as const;

/** One editable piece of ad content. `fields` are plain strings the seller can change; `savedId` is set once it is saved. */
type Draft = { key: string; kind: CreativeKind; fields: Record<string, string>; angle?: Angle; savedId?: number; aiGenerated: boolean };

let counter = 0;
const nextKey = () => `d${++counter}`;

function toDrafts(result: Creatives): Draft[] {
  const drafts: Draft[] = result.metaAds.map((a) => ({
    key: nextKey(), kind: "meta_ad", angle: a.angle, aiGenerated: true,
    fields: { hook: a.hook, primary_text: a.primary_text, headline: a.headline, cta: a.cta },
  }));
  if (result.instagram) drafts.push({ key: nextKey(), kind: "instagram", aiGenerated: true, fields: { caption: result.instagram.caption, hashtags: result.instagram.hashtags.join(" ") } });
  if (result.whatsappStatus) drafts.push({ key: nextKey(), kind: "whatsapp_status", aiGenerated: true, fields: { text: result.whatsappStatus.text } });
  return drafts;
}

function fromContent(kind: CreativeKind, content: Record<string, unknown>): Pick<Draft, "fields" | "angle"> {
  const str = (k: string) => (typeof content[k] === "string" ? (content[k] as string) : "");
  if (kind === "meta_ad") return { fields: { hook: str("hook"), primary_text: str("primary_text"), headline: str("headline"), cta: str("cta") }, angle: content.angle as Angle };
  if (kind === "instagram") return { fields: { caption: str("caption"), hashtags: Array.isArray(content.hashtags) ? (content.hashtags as string[]).join(" ") : "" } };
  return { fields: { text: str("text") } };
}

function toContent(d: Draft): Record<string, unknown> {
  if (d.kind === "meta_ad") return { ...d.fields, angle: d.angle };
  if (d.kind === "instagram") return { caption: d.fields.caption, hashtags: parseHashtags(d.fields.hashtags) };
  return { text: d.fields.text };
}

function asText(d: Draft): string {
  if (d.kind === "meta_ad") return adAsText({ hook: d.fields.hook, primary_text: d.fields.primary_text, headline: d.fields.headline, cta: d.fields.cta });
  if (d.kind === "instagram") return instagramAsText({ caption: d.fields.caption, hashtags: parseHashtags(d.fields.hashtags) });
  return d.fields.text;
}

/**
 * Step 4: the seller's brief goes to the AI, which writes ad copy. Everything it writes is an "AI suggestion" that
 * the seller can edit, regenerate one by one, copy and save. Copy that claims things nobody provided (a "sold"
 * count, reviews, fake scarcity) is removed by the server before it reaches this page.
 */
export function CreativeStudioBoard() {
  return <LaunchStepFrame step={4}>{(project) => <CreativeStep key={project.id} project={project} />}</LaunchStepFrame>;
}

function CreativeStep({ project }: { project: Project }) {
  const [name, setName] = useState(project.productName);
  const [features, setFeatures] = useState("");
  const [price, setPrice] = useState("");
  const [offer, setOffer] = useState("");
  const [target, setTarget] = useState("");
  const [language, setLanguage] = useState<Language>("roman_ur");
  const [tone, setTone] = useState<string>("Friendly");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [meta, setMeta] = useState<Creatives | null>(null);
  const [saved, setSaved] = useState<SavedCreative[]>([]);

  const loadSaved = useCallback(() => {
    listCreatives(project.id).then(setSaved).catch(() => undefined);
  }, [project.id]);
  useEffect(() => {
    loadSaved();
  }, [loadSaved]);

  function brief(): Brief | null {
    if (name.trim().length < 2) {
      setError("Give the product a name of at least 2 characters.");
      return null;
    }
    const money = Number(price.replace(/,/g, ""));
    return {
      productName: name.trim(), features: features.split("\n").map((f) => f.trim()).filter(Boolean).slice(0, 12),
      price: price.trim() && Number.isFinite(money) ? money : undefined, offer: offer.trim() || undefined,
      targetCustomer: target.trim() || undefined, language, tone: tone.toLowerCase(),
    };
  }

  async function generate(force: boolean) {
    setError(null);
    const b = brief();
    if (!b) return;
    setBusy(true);
    try {
      const result = await generateCreatives(project.id, b, force);
      setMeta(result);
      setDrafts((old) => [...toDrafts(result), ...old.filter((d) => d.savedId)]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const update = (key: string, patch: Partial<Draft>) => setDrafts((all) => all.map((d) => (d.key === key ? { ...d, ...patch } : d)));

  async function regenerate(d: Draft) {
    const b = brief();
    if (!b) return;
    try {
      const result = await regenerateCreative(project.id, d.kind, b, toContent(d));
      const next = fromContent(d.kind, result.content);
      update(d.key, { ...next, aiGenerated: true, savedId: undefined });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    }
  }

  async function save(d: Draft) {
    try {
      const row = d.savedId ? await editCreative(d.savedId, toContent(d)) : await saveCreative(project.id, d.kind, toContent(d), d.aiGenerated);
      update(d.key, { savedId: row.id, aiGenerated: row.aiGenerated });
      loadSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    }
  }

  function editSaved(item: SavedCreative) {
    const parts = fromContent(item.kind, item.content);
    setDrafts((all) => (all.some((d) => d.savedId === item.id) ? all : [{ key: nextKey(), kind: item.kind, savedId: item.id, aiGenerated: item.aiGenerated, ...parts }, ...all]));
  }

  async function removeSaved(item: SavedCreative) {
    await removeCreative(item.id).catch(() => undefined);
    setDrafts((all) => all.map((d) => (d.savedId === item.id ? { ...d, savedId: undefined } : d)));
    loadSaved();
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Tell the AI about your product</CardTitle>
          <CardDescription>The more real details you give, the better the copy. The AI is told not to invent anything, so it only uses what you write here.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <label className={field}>Product name<Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} /></label>
          <label className={field}>Price (PKR)<Input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} /></label>
          <label className={`${field} sm:col-span-2`}>Key features (one per line)<textarea className={areaClass} value={features} onChange={(e) => setFeatures(e.target.value)} dir="auto" /></label>
          <label className={field}>Offer (optional)<Input value={offer} onChange={(e) => setOffer(e.target.value)} maxLength={300} placeholder="for example: free delivery" /></label>
          <label className={field}>Who is it for? (optional)<Input value={target} onChange={(e) => setTarget(e.target.value)} maxLength={300} /></label>
          <div className={field}>
            <span>Language</span>
            <FilterPills label="Language" value={language} onChange={setLanguage}
              options={[{ value: "ur" as Language, label: "اردو" }, { value: "roman_ur" as Language, label: "Roman Urdu" }, { value: "en" as Language, label: "English" }]} />
          </div>
          <div className={field}>
            <span>Tone</span>
            <FilterPills label="Tone" value={tone} onChange={setTone} options={TONES.map((x) => ({ value: x as string, label: x }))} />
          </div>
          <div className="flex flex-wrap items-center gap-3 sm:col-span-2" aria-live="polite">
            <Button onClick={() => generate(false)} disabled={busy}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}
              Write ad copy with AI
            </Button>
            {meta ? <Button variant="secondary" onClick={() => generate(true)} disabled={busy}><RefreshCw className="h-4 w-4" aria-hidden="true" />Write all again</Button> : null}
            {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
          </div>
        </CardContent>
      </Card>

      {meta ? (
        <div className="space-y-1 text-xs text-muted">
          <p>
            <span className="rounded-full bg-accent/10 px-2 py-0.5 font-medium text-accent">AI suggestion</span>{" "}
            {meta.cached ? "Saved answer: no new AI call was made." : meta.model ? fmt("Written by {model}.", { model: meta.model }) : ""}{" "}
            {meta.usedCompetitorAnalysis ? "The gaps found in your competitor ads were used." : "No competitor analysis was used (do step 3 first for sharper copy)."}
          </p>
          {meta.removed > 0 ? <p>{fmt("{count} suggestions were removed because they made claims that cannot be proven (sold counts, reviews, fake scarcity).", { count: meta.removed })}</p> : null}
        </div>
      ) : null}

      {drafts.length > 0 ? (
        <section aria-label="Ad content" className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {drafts.map((d) => <DraftCard key={d.key} draft={d} onChange={(f) => update(d.key, { fields: { ...d.fields, ...f }, aiGenerated: false })} onRegenerate={() => regenerate(d)} onSave={() => save(d)} />)}
        </section>
      ) : null}

      {saved.length > 0 ? (
        <Card>
          <CardHeader><CardTitle>Saved to this project</CardTitle></CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {saved.map((item) => (
                <li key={item.id} className="flex flex-wrap items-start justify-between gap-2 rounded-xl border border-line bg-surface-2 p-3 text-sm">
                  <span className="min-w-0 flex-1 text-ink-2" dir="auto">
                    <strong className="text-ink">{KIND_LABEL[item.kind]}</strong>
                    {item.aiGenerated ? <span className="ml-2 text-xs text-muted">AI suggestion</span> : null}
                    <span className="mt-1 block whitespace-pre-wrap">{asText({ key: "", kind: item.kind, aiGenerated: item.aiGenerated, ...fromContent(item.kind, item.content) })}</span>
                  </span>
                  <span className="flex gap-1">
                    <CopyButton text={asText({ key: "", kind: item.kind, aiGenerated: item.aiGenerated, ...fromContent(item.kind, item.content) })} />
                    <Button variant="ghost" onClick={() => editSaved(item)} aria-label="Edit"><Pencil className="h-4 w-4" aria-hidden="true" /></Button>
                    <Button variant="ghost" onClick={() => removeSaved(item)} aria-label="Delete"><Trash2 className="h-4 w-4" aria-hidden="true" /></Button>
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Post image maker</CardTitle>
          <CardDescription>Make a simple picture for a post or story in your browser. No paid tool and no upload.</CardDescription>
        </CardHeader>
        <CardContent><PostImageMaker productName={name} /></CardContent>
      </Card>
    </div>
  );
}

const KIND_LABEL: Record<CreativeKind, string> = { meta_ad: "Meta ad", instagram: "Instagram post", whatsapp_status: "WhatsApp status" };

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button variant="ghost" aria-label="Copy" onClick={async () => { await navigator.clipboard?.writeText(text).catch(() => undefined); setDone(true); setTimeout(() => setDone(false), 1500); }}>
      {done ? <Check className="h-4 w-4" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
      <span className="text-xs">{done ? "Copied" : "Copy"}</span>
    </Button>
  );
}

function DraftCard({ draft, onChange, onRegenerate, onSave }: { draft: Draft; onChange: (f: Record<string, string>) => void; onRegenerate: () => void; onSave: () => void }) {
  const [busy, setBusy] = useState(false);
  const f = draft.fields;
  const input = (key: string, label: string, rows?: number) => (
    <label className={field}>
      {label}
      {rows ? <textarea className={areaClass} rows={rows} value={f[key]} onChange={(e) => onChange({ [key]: e.target.value })} dir="auto" /> : <Input value={f[key]} onChange={(e) => onChange({ [key]: e.target.value })} dir="auto" />}
    </label>
  );
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>{KIND_LABEL[draft.kind]}{draft.angle ? ` · ${ANGLE_LABEL[draft.angle]}` : ""}</CardTitle>
          <CardDescription>{draft.aiGenerated ? "AI suggestion: edit it as you like." : "Edited by you."}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {draft.kind === "meta_ad" ? (
          <>
            {input("hook", "Hook (first line)")}
            {input("primary_text", "Primary text", 4)}
            {input("headline", "Headline")}
            {input("cta", "Call to action")}
          </>
        ) : draft.kind === "instagram" ? (
          <>
            {input("caption", "Caption", 5)}
            {input("hashtags", "Hashtags (separated by spaces)")}
          </>
        ) : input("text", "Status text", 3)}
        <div className="flex flex-wrap gap-2">
          <CopyButton text={asText(draft)} />
          <Button variant="secondary" disabled={busy} onClick={async () => { setBusy(true); await onRegenerate(); setBusy(false); }}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
            Write another version
          </Button>
          <Button onClick={onSave}><Save className="h-4 w-4" aria-hidden="true" />{draft.savedId ? "Save changes" : "Save to project"}</Button>
        </div>
        {draft.savedId ? <p className="flex items-center gap-1.5 text-xs text-success"><Check className="h-3.5 w-3.5" aria-hidden="true" />Saved to this project</p> : null}
      </CardContent>
    </Card>
  );
}
