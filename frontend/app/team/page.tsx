import { PageHeader } from "@/components/page-header";
import { TeamBoard } from "@/components/team-board";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader title="Team" description="Who can sign in, and what each person may do. Only the owner sees this page." />
      <TeamBoard />
    </div>
  );
}
