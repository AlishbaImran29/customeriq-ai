"use client";

import { Users } from "lucide-react";
import { EmptyState } from "@/components/states";
import { useLanguage } from "@/lib/i18n";

/** Shown instead of the segments when there are too few customers: says HOW MANY more are needed. */
export function NeedMoreCustomers({ needed, minimum }: { needed: number; minimum: number }) {
  const { t, tf } = useLanguage();
  return (
    <EmptyState
      icon={Users}
      title={t("Not enough customers to segment")}
      description={tf("Not enough data yet: {count} more customers needed. Segmentation needs at least {minimum} customers.", {
        count: needed,
        minimum,
      })}
    />
  );
}

/** A channel filter with no orders: not an error, and a way back. */
export function NoOrdersInChannel({ channel }: { channel: string }) {
  const { t, tf } = useLanguage();
  return (
    <EmptyState
      icon={Users}
      title={tf("No {channel} orders yet", { channel })}
      description={t("There are no orders from this channel in your data. Add orders with Add Order, or choose another channel above.")}
    />
  );
}
