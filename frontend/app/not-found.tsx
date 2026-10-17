import Link from "next/link";
import { Compass } from "lucide-react";
import { EmptyState } from "@/components/states";

export default function NotFound() {
  return (
    <EmptyState
      className="mt-8"
      icon={Compass}
      title="Page not found"
      description="The page you're looking for doesn't exist or has moved."
      action={
        <Link
          href="/"
          className="inline-flex items-center rounded-xl bg-accent px-3.5 py-2 text-sm font-medium text-accent-ink hover:bg-accent-strong"
        >
          Back to dashboard
        </Link>
      }
    />
  );
}