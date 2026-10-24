import { PageHeader } from "@/components/page-header";
import { WorkflowBuilder } from "@/components/workflow-builder";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Workflows"
        description="Make the app do things for you: when something happens and your conditions hold, send a message, add a tag, make a to-do or change an order, after a wait if you like."
      />
      <WorkflowBuilder />
    </div>
  );
}
