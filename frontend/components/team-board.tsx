"use client";

import { useCallback, useEffect, useState } from "react";
import { formatWhen } from "@/components/messenger-bits";
import { ErrorState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { API_MODE, ApiError } from "@/lib/api/config";
import { ROLE_TEXT, changeMember, listMembers, type Member, type Role } from "@/lib/api/team";

/** Who can sign in and what they may do (owner only). The rules are enforced on the server; this page only changes the role. */
export function TeamBoard() {
  if (API_MODE !== "live") return <p className="text-sm text-muted">Team roles need the backend. Connect it to use them.</p>;
  return <TeamContent />;
}

function TeamContent() {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listMembers()
      .then((r) => !cancelled && (setMembers(r), setFailed(null)))
      .catch((e) => !cancelled && setFailed(e instanceof ApiError ? e.message : "x"));
    return () => {
      cancelled = true;
    };
  }, [version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  async function change(m: Member, patch: Partial<{ role: Role; isActive: boolean }>) {
    setError(null);
    try {
      await changeMember(m.id, patch);
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    }
  }

  if (failed) return <ErrorState title="Could not load the team" description={(failed === "x" ? "Please check your connection and reload the page." : failed)} />;
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader><CardTitle>Roles</CardTitle></CardHeader>
        <CardContent><ul className="space-y-1 text-sm text-ink-2">{(Object.keys(ROLE_TEXT) as Role[]).map((r) => <li key={r}>{ROLE_TEXT[r]}</li>)}</ul></CardContent>
      </Card>
      {!members ? <Skeleton className="h-32 w-full" /> : (
        <ul className="space-y-2">
          {members.map((m) => (
            <li key={m.id}>
              <Card><CardContent className="flex flex-wrap items-center gap-3 pt-5 text-sm">
                <span className="min-w-0 flex-1"><span className="font-medium text-ink">{m.name}</span> <span className="text-xs text-muted">{m.email}{m.lastLoginAt ? ` · ${"last sign-in"} ${formatWhen(m.lastLoginAt)}` : ""}</span></span>
                <Select value={m.role} onChange={(e) => change(m, { role: e.target.value as Role })} aria-label={`${"Role of"} ${m.name}`}>
                  <option value="owner">Owner</option><option value="staff">Staff</option><option value="viewer">Viewer</option>
                </Select>
                <label className="flex items-center gap-2 text-xs text-ink-2">
                  <input type="checkbox" checked={m.isActive} onChange={(e) => change(m, { isActive: e.target.checked })} className="h-4 w-4 accent-[var(--color-accent)]" />Can sign in
                </label>
              </CardContent></Card>
            </li>
          ))}
        </ul>
      )}
      <div aria-live="polite">{error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}</div>
      <p className="text-xs text-muted">New people who sign up start as Viewers. Raise their role here.</p>
    </div>
  );
}
