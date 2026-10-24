"use client";

import { useCallback, useEffect, useState } from "react";
import { GitMerge, Loader2 } from "lucide-react";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { API_MODE, ApiError } from "@/lib/api/config";
import { listAudit, listDuplicates, mergeCustomers, type AuditRow, type CustomerProfile, type DuplicateGroup } from "@/lib/api/customer-records";
import { useLanguage } from "@/lib/i18n";
import { formatDate } from "@/lib/utils";

const ACTION: Record<string, string> = { edit: "Edited", merge: "Merged", anonymise: "Personal data erased", delete: "Deleted" };

/** Customers who share an email address, with a safe merge (orders, messages and consent all move; an opt-out always wins), and the audit trail. */
export function DuplicatesBoard() {
  const { t } = useLanguage();
  if (API_MODE !== "live") return <p className="text-sm text-muted">{t("Customer records are saved in your database. Connect the backend to use them.")}</p>;
  return <DuplicatesContent />;
}

function DuplicatesContent() {
  const { t } = useLanguage();
  const [groups, setGroups] = useState<DuplicateGroup[] | null>(null);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listDuplicates()
      .then((r) => !cancelled && (setGroups(r), setFailed(false)))
      .catch(() => !cancelled && setFailed(true));
    listAudit().then((r) => !cancelled && setAudit(r)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (failed) return <ErrorState title={t("Could not load the duplicates")} description={t("Please check your connection and reload the page.")} />;
  return (
    <div className="space-y-5">
      {!groups ? <Skeleton className="h-40 w-full" /> : groups.length === 0 ? <p className="text-sm text-muted">{t("No duplicate customers found.")}</p> : (
        <ul className="space-y-3">{groups.map((g, i) => <Group key={i} group={g} onMerged={reload} />)}</ul>
      )}
      <Card>
        <CardHeader><CardTitle>{t("Audit trail")}</CardTitle><CardDescription>{t("Edits, merges and erasures. It never contains names, phones or emails.")}</CardDescription></CardHeader>
        <CardContent>
          {audit.length === 0 ? <p className="text-sm text-muted">{t("Nothing yet.")}</p> : (
            <ul className="space-y-1 text-sm text-ink-2">{audit.map((a) => <li key={a.id}>{formatDate(a.at)} · {t(ACTION[a.action] ?? a.action)} · {a.customerRef}</li>)}</ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Group({ group, onMerged }: { group: DuplicateGroup; onMerged: () => void }) {
  const { t } = useLanguage();
  const [keepId, setKeepId] = useState(group.customers[0].id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function merge() {
    const others = group.customers.filter((c) => c.id !== keepId);
    if (!window.confirm(t("Merge these customers into the selected one? The others disappear. This cannot be undone."))) return;
    setBusy(true);
    setError(null);
    try {
      for (const other of others) await mergeCustomers(keepId, other.id);
      onMerged();
    } catch (e) {
      setError(e instanceof ApiError ? t(e.message) : t("Something went wrong. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  const label = (c: CustomerProfile) => `${c.name}${c.email ? ` · ${c.email}` : ""}${c.phone ? ` · ${c.phone}` : ""}`;
  return (
    <li>
      <Card>
        <CardHeader><CardTitle className="text-base">{t("Same email address")}</CardTitle><CardDescription>{t("Keep this one:")}</CardDescription></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <ul className="space-y-1">
            {group.customers.map((c) => (
              <li key={c.id}>
                <label className="flex items-center gap-2 text-ink-2">
                  <input type="radio" name={`keep-${group.customers[0].id}`} checked={keepId === c.id} onChange={() => setKeepId(c.id)} className="h-4 w-4 accent-[var(--color-accent)]" />
                  {label(c)}
                </label>
              </li>
            ))}
          </ul>
          <div className="flex items-center gap-3" aria-live="polite">
            <Button onClick={merge} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <GitMerge className="h-4 w-4" aria-hidden="true" />}{t("Merge")}</Button>
            {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
          </div>
        </CardContent>
      </Card>
    </li>
  );
}
