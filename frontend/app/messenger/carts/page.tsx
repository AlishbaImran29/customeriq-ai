import { CartsBoard } from "@/components/carts-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Auto Messenger: Abandoned Carts"
        description="Shoppers who left a checkout. Reminders go only to customers who agreed to be messaged, and stop the moment they buy."
      />
      <CartsBoard />
    </div>
  );
}
