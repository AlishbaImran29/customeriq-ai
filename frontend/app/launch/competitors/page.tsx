import { Suspense } from "react";
import { CompetitorBoard } from "@/components/competitor-board";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Competitor Board"
        description="See how others advertise the same product, save the ads you like, and find the gaps you can use."
      />
      {/* The step bar reads the chosen project from the address, which needs a Suspense boundary. */}
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <CompetitorBoard />
      </Suspense>
    </div>
  );
}
