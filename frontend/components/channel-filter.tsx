"use client";

import { useRouter } from "next/navigation";
import { ChannelLabel } from "@/components/channel-icon";
import { FilterPills } from "@/components/ui/filter-pills";
import { CHANNELS } from "@/lib/quick-order";
import { fmt } from "@/lib/format";

type Choice = "all" | (typeof CHANNELS)[number]["value"];

/**
 * Limits the dashboard to one sales channel. The choice lives in the page address (like the dates), so
 * a filtered view can be bookmarked or shared. `keep` carries the chosen dates along.
 */
export function ChannelFilter({
  current,
  keep,
}: {
  current: string | null;
  keep: { from?: string; to?: string };
}) {
  const router = useRouter();
  function choose(value: Choice) {
    const params = new URLSearchParams();
    if (keep.from) params.set("from", keep.from);
    if (keep.to) params.set("to", keep.to);
    if (value !== "all") params.set("channel", value);
    const query = params.toString();
    router.push(query ? `/?${query}` : "/");
  }

  const label = (value: string, text: string) => (value === "other" ? "Other" : text);
  return (
    <div className="space-y-2">
      <FilterPills
        label="Filter by sales channel"
        options={[
          { value: "all" as Choice, label: "All channels" },
          ...CHANNELS.map((c) => ({
            value: c.value as Choice,
            label: <ChannelLabel channel={c.value}>{label(c.value, c.label)}</ChannelLabel>,
          })),
        ]}
        value={(current ?? "all") as Choice}
        onChange={choose}
      />
      {current ? (
        <p className="text-xs text-muted">
          {fmt("Showing figures for {channel} orders only.", {
            channel: label(current, CHANNELS.find((c) => c.value === current)?.label ?? current),
          })}
        </p>
      ) : null}
    </div>
  );
}
