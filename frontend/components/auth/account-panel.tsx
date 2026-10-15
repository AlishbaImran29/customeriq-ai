"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { changePassword, getMe, type AuthUser } from "@/lib/api/auth";
import { API_MODE, ApiError } from "@/lib/api/config";
import { formatDate } from "@/lib/utils";

const MIN_PASSWORD_LENGTH = 10;

export function AccountPanel() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (API_MODE === "demo") return;
    let cancelled = false;
    getMe()
      .then((me) => !cancelled && setUser(me))
      .catch((error: unknown) => {
        if (!cancelled) setLoadError(error instanceof ApiError ? error.message : "Could not load your account.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (API_MODE === "demo") {
    return (
      <Card>
        <CardContent className="pt-5 text-sm text-slate-600">
          Accounts are not used in demo mode. Connect the backend to turn on sign-in.
        </CardContent>
      </Card>
    );
  }
  if (loadError) {
    return (
      <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900">
        {loadError}
      </p>
    );
  }
  if (!user) return <Skeleton className="h-64 rounded-2xl" />;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Your account</CardTitle>
          <CardDescription>The details you signed up with.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-xs text-slate-500">Name</dt>
              <dd className="font-medium text-slate-900">{user.name}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Email</dt>
              <dd className="font-medium text-slate-900">{user.email}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Last sign-in</dt>
              <dd className="font-medium text-slate-900">{user.lastLoginAt ? formatDate(user.lastLoginAt) : "This is your first sign-in"}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
      <PasswordForm />
    </div>
  );
}

function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<{ message: string; field?: string } | null>(null);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setDone(false);
    if (!current) return setError({ message: "Please enter your current password.", field: "currentPassword" });
    if (next.length < MIN_PASSWORD_LENGTH) {
      return setError({ message: `Your new password needs at least ${MIN_PASSWORD_LENGTH} characters.`, field: "newPassword" });
    }
    if (next !== confirm) return setError({ message: "The two new passwords don't match yet.", field: "confirm" });
    setError(null);
    setBusy(true);
    try {
      await changePassword(current, next);
      setDone(true);
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (cause) {
      if (cause instanceof ApiError) {
        const field = (cause.details as { field?: string } | null)?.field;
        setError({ message: cause.message, field });
      } else {
        setError({ message: "Something went wrong. Please try again." });
      }
    } finally {
      setBusy(false);
    }
  }

  const fieldError = (field: string) => (error?.field === field ? error.message : undefined);
  const general = error && !error.field ? error.message : undefined;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Change password</CardTitle>
        <CardDescription>Other devices where you&apos;re signed in will be signed out.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <Field id="current" label="Current password" error={fieldError("currentPassword")}>
            <Input id="current" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} className="h-11" />
          </Field>
          <Field id="new" label="New password" error={fieldError("newPassword")} hint={`At least ${MIN_PASSWORD_LENGTH} characters. A few unrelated words work well.`}>
            <Input id="new" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} className="h-11" />
          </Field>
          <Field id="confirm-new" label="Confirm new password" error={fieldError("confirm")}>
            <Input id="confirm-new" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="h-11" />
          </Field>

          {general ? (
            <p role="alert" className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              {general}
            </p>
          ) : null}
          {done ? (
            <p role="status" className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              Password changed. Your other devices were signed out.
            </p>
          ) : null}

          <Button type="submit" disabled={busy}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
            {busy ? "Saving…" : "Change password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-slate-800">
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="mt-1.5 flex items-start gap-1.5 text-sm text-rose-700">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1.5 text-xs text-slate-500">{hint}</p>
      ) : null}
    </div>
  );
}
