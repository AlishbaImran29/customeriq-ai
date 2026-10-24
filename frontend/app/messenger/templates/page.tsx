import { MessengerTemplatesBoard } from "@/components/messenger-templates-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Auto Messenger: Templates"
        description="The wording of every automatic message, in English and Urdu. Nothing is sent from a template until you approve it."
      />
      <MessengerTemplatesBoard />
    </div>
  );
}
