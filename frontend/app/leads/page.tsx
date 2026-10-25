import { LeadsBoard } from "@/components/leads-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Leads"
        description="People who showed interest but have not bought yet. Contact new leads quickly, and convert them into customers without losing where they came from."
      />
      <LeadsBoard />
    </div>
  );
}
