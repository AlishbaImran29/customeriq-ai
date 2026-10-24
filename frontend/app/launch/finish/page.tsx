import { Suspense } from "react";
import { LaunchFinishBoard } from "@/components/launch-finish-board";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Launch"
        description="Mark the product as launched and see how it really sells, from your own orders."
      />
      {/* The step bar reads the chosen project from the address, which needs a Suspense boundary. */}
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <LaunchFinishBoard />
      </Suspense>
    </div>
  );
}
