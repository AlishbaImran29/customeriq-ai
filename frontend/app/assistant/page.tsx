import { Info, PlugZap } from "lucide-react";
import { AssistantChat } from "@/components/assistant-chat";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const topics = [
  "Churn risk and customers likely to leave",
  "Revenue changes month over month",
  "Most valuable segments",
  "Customer lifetime value trends",
  "Retention performance",
  "Health score drivers",
  "Upsell and cross-sell opportunities",
];

export default function AssistantPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Business Assistant"
        description="Ask questions about your customers in plain language, such as who is likely to churn, why revenue moved, or which segment is most valuable."
      />
      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Growth copilot</CardTitle>
            <CardDescription>Answers are drawn from your customer intelligence data.</CardDescription>
          </CardHeader>
          <CardContent>
            <AssistantChat />
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card className="border-amber-200 bg-amber-50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-amber-900">
                <PlugZap className="h-4 w-4" aria-hidden="true" /> Sample mode
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-amber-900">
              No AI model is connected. Replies are pre-written sample answers matched by keyword.
              Live answers will come from the backend assistant service, which keeps all API keys
              server-side.
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Info className="h-4 w-4 text-teal-600" aria-hidden="true" /> Topics covered
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1.5 text-sm text-slate-600">
                {topics.map((topic) => (
                  <li key={topic} className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-600" aria-hidden="true" />
                    {topic}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}