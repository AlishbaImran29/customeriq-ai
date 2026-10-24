import { Suspense } from "react";
import { CreativeStudioBoard } from "@/components/creative-studio-board";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Creative Studio"
        description="Write ad copy, captions and status text with AI, edit them, and make a simple post image."
      />
      {/* The step bar reads the chosen project from the address, which needs a Suspense boundary. */}
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <CreativeStudioBoard />
      </Suspense>
    </div>
  );
}
