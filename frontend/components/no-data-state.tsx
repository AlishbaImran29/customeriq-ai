"use client";

import Link from "next/link";
import { FileUp } from "lucide-react";
import { EmptyState } from "@/components/states";

export function NoDataState() {
  return (
    <EmptyState
      icon={FileUp}
      title="No customer data yet"
      description="Import a CSV or Excel file of orders to see this page with your own data."
      action={
        <Link
          href="/import"
          className="inline-flex items-center rounded-xl bg-accent px-3.5 py-2 text-sm font-medium text-accent-ink hover:bg-accent-strong"
        >
          Import data
        </Link>
      }
    />
  );
}
