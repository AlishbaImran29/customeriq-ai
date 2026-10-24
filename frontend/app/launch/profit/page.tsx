import { Suspense } from "react";
import { ProfitCheckBoard } from "@/components/profit-check-board";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Profit Check"
        description="Check that the product makes money after returns and ads, before you spend on ads."
      />
      {/* The step bar reads the chosen project from the address, which needs a Suspense boundary. */}
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <ProfitCheckBoard />
      </Suspense>
    </div>
  );
}
