import type { Metadata } from "next";
import { Suspense } from "react";
import { LoginForm } from "@/components/auth/login-form";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Sign in · CustomerIQ AI" };

export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-4 py-10">
      <div className="flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent text-base font-bold text-accent-ink">
          IQ
        </span>
        <span>
          <span className="block text-lg font-semibold text-ink">CustomerIQ AI</span>
          <span className="block text-xs text-muted">Predictive customer intelligence</span>
        </span>
      </div>
      <Suspense fallback={<Skeleton className="h-96 w-full max-w-md rounded-2xl" />}>
        <LoginForm />
      </Suspense>
      <p className="max-w-sm text-center text-xs text-faint">
        Your customer data is only shown after you sign in.
      </p>
    </main>
  );
}
