import type { Metadata } from "next";
import { AccountPanel } from "@/components/auth/account-panel";
import { PageHeader } from "@/components/page-header";

export const metadata: Metadata = { title: "Account · CustomerIQ AI" };

export default function AccountPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Account" description="Your sign-in details and password." />
      <AccountPanel />
    </div>
  );
}
