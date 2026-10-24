import { MessengerResultsBoard } from "@/components/messenger-results-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Auto Messenger: Messaging Results"
        description="What the messages did: delivery, orders, revenue, and messaged versus not messaged."
      />
      <MessengerResultsBoard />
    </div>
  );
}
