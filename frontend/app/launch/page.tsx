import { Suspense } from "react";
import { LaunchProjectsBoard } from "@/components/launch-projects-board";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Launch Studio"
        description="Take a product idea from trend to launch in one place: find it, source it, check the profit, and track the results."
      />
      {/* The step bar reads the chosen project from the address, which needs a Suspense boundary. */}
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <LaunchProjectsBoard />
      </Suspense>
    </div>
  );
}
