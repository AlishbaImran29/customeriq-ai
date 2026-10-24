import { MessengerJourneysBoard } from "@/components/messenger-journeys-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Auto Messenger: Journeys"
        description="Automatic follow-ups for each customer segment, with a holdout group to prove they work."
      />
      <MessengerJourneysBoard />
    </div>
  );
}
