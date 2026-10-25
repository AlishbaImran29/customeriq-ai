import { MetaAdsBoard } from "@/components/meta-ads-board";
import { PageHeader } from "@/components/page-header";

export default function Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Meta Ads"
        description="Share customers who agreed with Meta as hashed audiences, tell Meta about delivered purchases only, and compare what Meta claims with your real delivered revenue."
      />
      <MetaAdsBoard />
    </div>
  );
}
