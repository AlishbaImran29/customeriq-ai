import { MessengerSettingsBoard } from "@/components/messenger-settings-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Auto Messenger: Settings"
        description="Connect WhatsApp and email, set quiet hours and the weekly limit, and send a test message."
      />
      <MessengerSettingsBoard />
    </div>
  );
}
