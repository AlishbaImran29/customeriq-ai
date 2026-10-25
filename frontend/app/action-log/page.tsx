import { PageHeader } from "@/components/page-header";
import { ActionLogBoard } from "@/components/team-board";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader title="Action Log" description="Every change anyone made, and every action that was refused. It never shows what was typed. Only the owner sees this page." />
      <ActionLogBoard />
    </div>
  );
}
