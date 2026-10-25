import { InboxBoard } from "@/components/inbox-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Inbox"
        description="Customer WhatsApp messages in one place, with replies drafted only from your own records. Complaints, returns and refunds are left to a person."
      />
      <InboxBoard />
    </div>
  );
}
