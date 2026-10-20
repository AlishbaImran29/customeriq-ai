import { CashTrackerBoard } from "@/components/cash-tracker-board";
import { PageHeader } from "@/components/page-header";

export default function CashPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Cash Tracker"
        description="Cash on delivery money the couriers have collected for you and not paid yet."
      />
      <CashTrackerBoard />
    </div>
  );
}
