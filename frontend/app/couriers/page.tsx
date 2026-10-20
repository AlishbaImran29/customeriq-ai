import { PageHeader } from "@/components/page-header";
import { CourierScorecardBoard } from "@/components/courier-scorecard-board";

export default function CouriersPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Courier Scorecard"
        description="How each courier did in each city: deliveries, returns and delivery time."
      />
      <CourierScorecardBoard />
    </div>
  );
}
