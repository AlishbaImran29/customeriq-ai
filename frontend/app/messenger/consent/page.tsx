import { MessengerConsentBoard } from "@/components/messenger-consent-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Auto Messenger: Consent"
        description="Who agreed to be messaged, and on which channel."
      />
      <MessengerConsentBoard />
    </div>
  );
}
