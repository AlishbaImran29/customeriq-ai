import { Suspense } from "react";
import { VendorBookBoard } from "@/components/vendor-book-board";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Vendor Book"
        description="Keep your suppliers in one place, compare their quotes side by side, and ask for a quote on WhatsApp."
      />
      {/* The step bar reads the chosen project from the address, which needs a Suspense boundary. */}
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <VendorBookBoard />
      </Suspense>
    </div>
  );
}
