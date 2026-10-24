"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Rocket } from "lucide-react";
import { LaunchSteps } from "@/components/launch-steps";
import { EmptyState, ErrorState } from "@/components/states";
import { Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { LAUNCH_AVAILABLE, listProjects, type Project } from "@/lib/api/launch";
import { useLanguage } from "@/lib/i18n";

/**
 * The frame every per-project step (2 to 6) sits in: the step bar, a picker for which launch project you are
 * working on, and the right messages when there is no backend or no project yet. Its children get the project.
 */
export function LaunchStepFrame({ step, children }: { step: number; children: (project: Project, reload: () => void) => React.ReactNode }) {
  const { t } = useLanguage();
  const router = useRouter();
  const pathname = usePathname();
  const wanted = Number(useSearchParams().get("project"));
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!LAUNCH_AVAILABLE) return;
    let cancelled = false;
    listProjects()
      .then((p) => !cancelled && (setProjects(p), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [version]);

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
  if (!projects) return <Skeleton className="h-64 w-full" />;

  const project = projects.find((p) => p.id === wanted) ?? projects[0] ?? null;
  return (
    <div className="space-y-5">
      <LaunchSteps current={step} />
      {project ? (
        <>
          <label className="block max-w-md space-y-1 text-xs font-medium text-muted">
            {t("Launch project")}
            <Select value={project.id} onChange={(e) => router.replace(`${pathname}?project=${e.target.value}`)} className="w-full">
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.productName}</option>
              ))}
            </Select>
          </label>
          {children(project, () => setVersion((v) => v + 1))}
        </>
      ) : (
        <EmptyState
          icon={Rocket}
          title={t("Start a launch project first")}
          description={t("Every step works on one product idea. Add one, then come back here.")}
          action={<Link href="/launch" className="text-sm font-medium text-accent underline underline-offset-2">{t("Go to Launch projects")}</Link>}
        />
      )}
    </div>
  );
}
