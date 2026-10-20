import { PageHeader } from "@/components/page-header";
import { SeasonForecastBoard } from "@/components/season-forecast-board";

export default function SeasonsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Season Forecast"
        description="How many units of each product to expect at Eid, Christmas and other seasons, shown only when it beats last year's sales."
      />
      <SeasonForecastBoard />
    </div>
  );
}
