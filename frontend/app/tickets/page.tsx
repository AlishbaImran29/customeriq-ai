import { PageHeader } from "@/components/page-header";
import { TicketsBoard } from "@/components/tickets-board";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader title="Complaints" description="Complaints and questions to follow up, with an owner, a status and notes." />
      <TicketsBoard />
    </div>
  );
}
