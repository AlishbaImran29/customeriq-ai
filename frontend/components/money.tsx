import { formatMoney } from "@/lib/currency";

/** A money amount in rupees (Rs.). */
export function Money({ value, compact = false }: { value: number; compact?: boolean }) {
  return <>{formatMoney(value, compact)}</>;
}
