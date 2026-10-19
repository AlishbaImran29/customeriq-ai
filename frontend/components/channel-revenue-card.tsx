"use client";

import { ChannelRevenueChart } from "@/components/charts/dashboard-charts";
import { Money } from "@/components/money";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useLanguage } from "@/lib/i18n";
import { CHANNELS } from "@/lib/quick-order";
import type { ChannelRevenue } from "@/lib/types";
import { formatDate, formatNumber, formatPercent } from "@/lib/utils";

/** "Revenue by channel": a bar chart and, under it, the same numbers as a table (so nothing depends on colour or on seeing the chart). */
export function ChannelRevenueCard({
  channels,
  start,
  end,
}: {
  channels: ChannelRevenue[];
  start: string | null;
  end: string | null;
}) {
  const { t, tf } = useLanguage();
  const name = (channel: string) =>
    channel === "other" ? t("Other") : (CHANNELS.find((c) => c.value === channel)?.label ?? channel);
  const total = channels.reduce((sum, c) => sum + c.revenue, 0);
  const rows = channels.map((c) => ({ ...c, label: name(c.channel) }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("Revenue by channel")}</CardTitle>
        <CardDescription>
          {start && end
            ? tf("Where the orders came from, {start} to {end}. All channels are shown, whatever the filter is.", {
                start: formatDate(start),
                end: formatDate(end),
              })
            : t("Where the orders came from.")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {total > 0 ? <ChannelRevenueChart data={rows} /> : null}
        <div className="relative overflow-x-auto">
          <table className="w-full min-w-[420px] text-left text-sm">
            <caption className="sr-only">{t("Revenue, orders and customers for each sales channel")}</caption>
            <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <tr>
                <th scope="col" className="py-2 pr-3 font-medium">{t("Channel")}</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">{t("Revenue")}</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">{t("Share of revenue")}</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">{t("Orders")}</th>
                <th scope="col" className="py-2 pl-3 text-right font-medium">{t("Customers")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.channel} className="border-b border-line/60 last:border-0">
                  <th scope="row" className="py-2 pr-3 text-left font-medium text-ink">{row.label}</th>
                  <td className="px-3 py-2 text-right tabular-nums"><Money value={row.revenue} /></td>
                  <td className="px-3 py-2 text-right tabular-nums">{total > 0 ? formatPercent((row.revenue / total) * 100) : "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatNumber(row.orders)}</td>
                  <td className="py-2 pl-3 text-right tabular-nums">{formatNumber(row.customers)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
