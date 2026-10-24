"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useLanguage } from "@/lib/i18n";

export type ChurnReason = { template: string; params: Record<string, string>; text: string };

/**
 * "Why this risk?": up to three reasons the churn model gives for one customer. Each reason was measured by asking the model again
 * with that one input set to a typical value; a reason is listed only if that really lowered the predicted risk.
 */
export function ChurnReasons({ reasons }: { reasons: ChurnReason[] }) {
  const { t, tf } = useLanguage();
  if (reasons.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Why this risk?")}</CardTitle>
        <CardDescription>{t("The biggest signals behind this customer's churn estimate. An estimate, not a certainty.")}</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">
          {reasons.map((r) => <li key={r.template}>{tf(r.template, r.params)}</li>)}
        </ul>
      </CardContent>
    </Card>
  );
}
