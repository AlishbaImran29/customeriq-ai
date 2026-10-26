import { EmailAutomationsBoard } from "@/components/email-automations-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Email Automations"
        description="COD confirmation emails, win-back emails for customers who stopped buying, and new-product emails. Every email is personalised for one customer."
      />
      <EmailAutomationsBoard />
    </div>
  );
}
