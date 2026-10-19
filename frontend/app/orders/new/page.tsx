import { ClipboardPlus } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { QuickOrderForm } from "@/components/quick-order-form";
import { EmptyState } from "@/components/states";
import { QUICK_ORDER_AVAILABLE } from "@/lib/api/orders";

export default function AddOrderPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Add Order"
        description="Add an order you received in a chat in about ten seconds. It joins your customers and reports like any imported order."
      />
      {QUICK_ORDER_AVAILABLE ? (
        <QuickOrderForm />
      ) : (
        <EmptyState
          icon={ClipboardPlus}
          title="Adding orders needs the backend"
          description="Demo mode has no database to save to. Connect the backend (NEXT_PUBLIC_API_BASE_URL) to add orders."
        />
      )}
    </div>
  );
}
