import { DuplicatesBoard } from "@/components/duplicates-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Duplicate Customers"
        description="Find customers who look like the same person, merge them safely, and see every merge and erasure."
      />
      <DuplicatesBoard />
    </div>
  );
}
