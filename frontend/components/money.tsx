import { formatMoney } from "@/lib/currency";

/** A money amount in pounds (£). */
export function Money({ value, compact = false }: { value: number; compact?: boolean }) {
  return <>{formatMoney(value, compact)}</>;
}
