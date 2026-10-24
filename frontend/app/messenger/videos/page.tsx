import { MessengerVideosBoard } from "@/components/messenger-videos-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Auto Messenger: Customer Videos"
        description="Photos and videos customers sent you, and whether you may use them in ads."
      />
      <MessengerVideosBoard />
    </div>
  );
}
