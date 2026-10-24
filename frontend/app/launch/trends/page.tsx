import { Suspense } from "react";
import { TrendFinderBoard } from "@/components/trend-finder-board";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Trend Finder"
        description="See what people search for, which of your own products are growing, and get product ideas to launch."
      />
      {/* The step bar reads the chosen project from the address, which needs a Suspense boundary. */}
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <TrendFinderBoard />
      </Suspense>
    </div>
  );
}
