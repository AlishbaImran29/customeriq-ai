import { MessengerOrdersBoard } from "@/components/messenger-orders-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Auto Messenger: Order Updates"
        description="Change an order's status and tell the customer on WhatsApp or email."
      />
      <MessengerOrdersBoard />
    </div>
  );
}
