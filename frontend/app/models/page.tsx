import { ModelReportBoard } from "@/components/model-report-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Model Report Card"
        description="Every prediction model next to a simple baseline, tested on newer data it did not train on. A model that does not beat its baseline is hidden."
      />
      <ModelReportBoard />
    </div>
  );
}
