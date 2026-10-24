import { MessengerMessagesBoard } from "@/components/messenger-messages-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Auto Messenger: Messages"
        description="Every message the app tried to send, and why a message was not sent."
      />
      <MessengerMessagesBoard />
    </div>
  );
}
