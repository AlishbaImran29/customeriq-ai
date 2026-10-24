"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Archive, CheckCircle2, Lightbulb, Loader2, PackageCheck, Plus, Rocket, Trash2, Truck } from "lucide-react";
import { LaunchSteps } from "@/components/launch-steps";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/config";
import {
  LAUNCH_AVAILABLE, STATUSES, createProject, deleteProject, listProjects, updateProject,
  type Project, type Status,
} from "@/lib/api/launch";
import { useLanguage } from "@/lib/i18n";
import { formatDate } from "@/lib/utils";

const STATUS_LOOK: Record<Status, { label: string; icon: typeof Lightbulb }> = {
  idea: { label: "Idea", icon: Lightbulb },
  sourcing: { label: "Sourcing", icon: Truck },
  ready: { label: "Ready", icon: PackageCheck },
  launched: { label: "Launched", icon: Rocket },
  dropped: { label: "Dropped", icon: Archive },
};

/** The seller's launch projects: start one, change its status, or delete it. Each one is saved, so they can come back to it. */
export function LaunchProjectsBoard() {
  const { t, tf } = useLanguage();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);

  const load = useCallback(() => {
    listProjects()
      .then((p) => (setProjects(p), setFailed(false)))
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    if (LAUNCH_AVAILABLE) load();
  }, [load]);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (name.trim().length < 2) return setError(t("Give the product a name of at least 2 characters."));
    setBusy(true);
    try {
      await createProject({ productName: name.trim(), category: category.trim() || undefined });
      setName("");
      setCategory("");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  async function change(id: number, status: Status) {
    try {
      await updateProject(id, { status });
      load();
    } catch {
      setError(t("Something went wrong. Please try again."));
    }
  }

  async function remove(id: number) {
    try {
      await deleteProject(id);
      setConfirming(null);
      load();
    } catch {
      setError(t("Something went wrong. Please try again."));
    }
  }

  if (!LAUNCH_AVAILABLE) {
    return (
      <EmptyState
        icon={Rocket}
        title={t("Launch Studio needs the backend")}
        description={t("Launch projects are saved in your database. Connect the backend to use Launch Studio.")}
      />
    );
  }
  if (failed) return <ErrorState title={t("Could not load your launch projects")} description={t("Please check your connection and reload the page.")} />;

  return (
    <div className="space-y-5">
      <LaunchSteps current={1} />
      <Card>
        <CardHeader>
          <CardTitle>{t("Start a launch project")}</CardTitle>
          <CardDescription>{t("One project for each product you are thinking of selling. You can come back to it later.")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={add} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]" noValidate>
            <label className="space-y-1 text-xs font-medium text-muted">
              {t("Product name")}
              <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
            </label>
            <label className="space-y-1 text-xs font-medium text-muted">
              {t("Category (optional)")}
              <Input value={category} onChange={(e) => setCategory(e.target.value)} maxLength={100} />
            </label>
            <div className="flex items-end">
              <Button type="submit" disabled={busy} className="w-full sm:w-auto">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />}
                {t("Add project")}
              </Button>
            </div>
          </form>
          <div aria-live="polite">{error ? <p role="alert" className="mt-2 text-sm text-danger">{error}</p> : null}</div>
          <p className="mt-3 text-sm text-ink-2">
            {t("No idea yet?")}{" "}
            <Link href="/launch/trends" className="font-medium text-accent underline underline-offset-2">{t("Open the Trend Finder")}</Link>
          </p>
        </CardContent>
      </Card>

      {!projects ? (
        <Skeleton className="h-40 w-full" />
      ) : projects.length === 0 ? (
        <EmptyState icon={Rocket} title={t("No launch projects yet")} description={t("Add your first product idea above, or find one in the Trend Finder.")} />
      ) : (
        <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {projects.map((p) => {
            const look = STATUS_LOOK[p.status];
            const Icon = look.icon;
            return (
              <li key={p.id}>
                <Card className="h-full">
                  <CardContent className="space-y-3 pt-5">
                    <div>
                      <p className="text-base font-semibold text-ink">{p.productName}</p>
                      <p className="text-xs text-muted">
                        {p.category ? `${p.category} · ` : ""}
                        {tf("Started {date}", { date: formatDate(p.createdAt.slice(0, 10)) })}
                        {p.launchedOn ? ` · ${tf("Launched {date}", { date: formatDate(p.launchedOn) })}` : ""}
                      </p>
                    </div>
                    <p className="inline-flex items-center gap-1.5 rounded-full bg-surface-3 px-2.5 py-1 text-xs font-medium text-ink-2">
                      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                      {t(look.label)}
                    </p>
                    <label className="block space-y-1 text-xs font-medium text-muted">
                      {t("Status")}
                      <Select value={p.status} onChange={(e) => change(p.id, e.target.value as Status)} className="w-full">
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>{t(STATUS_LOOK[s].label)}</option>
                        ))}
                      </Select>
                    </label>
                    {confirming === p.id ? (
                      <div className="flex flex-wrap items-center gap-2">
                        <Button onClick={() => remove(p.id)} className="bg-danger text-white hover:bg-danger/90">
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                          {t("Yes, delete")}
                        </Button>
                        <Button variant="secondary" onClick={() => setConfirming(null)}>{t("Cancel")}</Button>
                      </div>
                    ) : (
                      <Button variant="ghost" onClick={() => setConfirming(p.id)} aria-label={tf("Delete {product}", { product: p.productName })}>
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                        {t("Delete")}
                      </Button>
                    )}
                  </CardContent>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
      <p className="flex items-center gap-1.5 text-xs text-muted">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
        {t("Next steps (vendors, competitors, creatives, profit check and launch) are coming.")}
      </p>
    </div>
  );
}
