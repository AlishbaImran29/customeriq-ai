"use client";

import { useRouter } from "next/navigation";
import { FilterPills } from "@/components/ui/filter-pills";
import { useLanguage } from "@/lib/i18n";
import { CHANNELS } from "@/lib/quick-order";
import type { ChannelRevenue } from "@/lib/types";
import { formatNumber } from "@/lib/utils";

type Choice = "all" | (typeof CHANNELS)[number]["value"];

/**
 * Limits the dashboard to one sales channel. The choice lives in the page address (like the dates), so
 * a filtered view can be bookmarked or shared. `keep` carries the chosen dates along.
 */
export function ChannelFilter({
  current,
  channels,
  keep,
}: {
  current: string | null;
  channels: ChannelRevenue[];
  keep: { from?: string; to?: string };
}) {
  const router = useRouter();
  const { t, tf } = useLanguage();
  const orders = (channel: string) => channels.find((c) => c.channel === channel)?.orders ?? 0;
  const total = channels.reduce((sum, c) => sum + c.orders, 0);

  function choose(value: Choice) {
    const params = new URLSearchParams();
    if (keep.from) params.set("from", keep.from);
    if (keep.to) params.set("to", keep.to);
    if (value !== "all") params.set("channel", value);
    const query = params.toString();
    router.push(query ? `/?${query}` : "/");
  }

  const label = (value: string, text: string) => (value === "other" ? t("Other") : text);
  return (
    <div className="space-y-2">
      <FilterPills
        label={t("Filter by sales channel")}
        options={[
          { value: "all" as Choice, label: t("All channels"), count: total },
          ...CHANNELS.map((c) => ({ value: c.value as Choice, label: label(c.value, c.label), count: orders(c.value) })),
        ]}
        value={(current ?? "all") as Choice}
        onChange={choose}
      />
      {current ? (
        <p className="text-xs text-muted">
          {tf("Showing figures for {channel} orders only. The revenue by channel chart below still compares all channels.", {
            channel: label(current, CHANNELS.find((c) => c.value === current)?.label ?? current),
          })}{" "}
          <span className="sr-only">{formatNumber(orders(current))}</span>
        </p>
      ) : null}
    </div>
  );
}
