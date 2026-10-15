"use client";

import { useCurrency } from "@/lib/currency";

/** A money amount in the currency the person chose in the header. */
export function Money({ value, compact = false }: { value: number; compact?: boolean }) {
  const { format, formatCompact } = useCurrency();
  return <>{compact ? formatCompact(value) : format(value)}</>;
}
