import { PageHeader } from "@/components/page-header";
import { ProfitBoard } from "@/components/profit-board";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Real Profit"
        description="Revenue, delivered revenue and profit after every cost, by product, channel, city and courier. Estimates are labelled, and unknown costs are named, never guessed."
      />
      <ProfitBoard />
    </div>
  );
}
