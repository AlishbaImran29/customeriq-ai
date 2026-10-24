import { LaunchProjectsBoard } from "@/components/launch-projects-board";
import { PageHeader } from "@/components/page-header";

export default function LaunchPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Launch Studio"
        description="Take a product idea from trend to launch in one place: find it, source it, check the profit, and track the results."
      />
      <LaunchProjectsBoard />
    </div>
  );
}
