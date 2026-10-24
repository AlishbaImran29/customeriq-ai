import { MessengerCodBoard } from "@/components/messenger-cod-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Auto Messenger: COD Confirmation"
        description="Cash-on-delivery customers are asked to confirm on WhatsApp. YES confirms, NO cancels, and no answer means a phone call."
      />
      <MessengerCodBoard />
    </div>
  );
}
