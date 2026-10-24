import { InventoryBoard } from "@/components/inventory-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Inventory"
        description="Count what you have. Confirmed orders reserve stock, dispatched orders sell it, and every change is kept."
      />
      <InventoryBoard />
    </div>
  );
}
