import { MessengerCampaignsBoard } from "@/components/messenger-campaigns-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Auto Messenger: Product Announcements"
        description="Tell the right customers about a new product, with an AI draft you approve."
      />
      <MessengerCampaignsBoard />
    </div>
  );
}
