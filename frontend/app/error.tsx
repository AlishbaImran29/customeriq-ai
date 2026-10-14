"use client";

import { useEffect } from "react";
import Link from "next/link";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";

export default function Error({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <ErrorState
      className="mt-8"
      title="We couldn't load this page"
      description={
        error.digest
          ? `An unexpected error occurred. Reference: ${error.digest}`
          : "An unexpected error occurred while loading customer intelligence data."
      }
      action={
        <div className="flex gap-2">
          <Button onClick={() => retry()}>Try again</Button>
          <Link
            href="/"
            className="inline-flex items-center rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Go to dashboard
          </Link>
        </div>
      }
    />
  );
}