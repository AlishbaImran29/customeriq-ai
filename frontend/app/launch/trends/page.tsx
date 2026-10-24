import { PageHeader } from "@/components/page-header";
import { TrendFinderBoard } from "@/components/trend-finder-board";

export default function TrendFinderPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Trend Finder"
        description="See what people search for, which of your own products are growing, and get product ideas to launch."
      />
      <TrendFinderBoard />
    </div>
  );
}
