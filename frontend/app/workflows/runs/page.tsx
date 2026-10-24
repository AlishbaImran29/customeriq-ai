import { PageHeader } from "@/components/page-header";
import { WorkflowRunsBoard } from "@/components/workflow-runs-board";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Workflow Logs"
        description="Every run of every workflow, step by step, with the facts it saw. Failed steps can be tried again."
      />
      <WorkflowRunsBoard />
    </div>
  );
}
