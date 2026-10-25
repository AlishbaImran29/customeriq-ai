import { PageHeader } from "@/components/page-header";
import { ReturnsBoard } from "@/components/returns-board";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Returns and Refunds"
        description="Approve or reject return requests, send a replacement, mark goods received, and record refunds you paid. The app never moves money."
      />
      <ReturnsBoard />
    </div>
  );
}
