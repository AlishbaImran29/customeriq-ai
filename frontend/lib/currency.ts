// Every amount in the app is shown in British pounds (£): the dataset (Online Retail II) is from a UK store, and the numbers
// are shown exactly as stored. There is no currency choice and no exchange rate.

const FORMATTER = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 2 });
const WHOLE_FORMATTER = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const COMPACT_FORMATTER = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", notation: "compact", maximumFractionDigits: 1 });

/** £1,234 for large amounts, £12.50 for small ones. */
export function formatMoney(value: number, compact = false): string {
  if (compact) return COMPACT_FORMATTER.format(value);
  return (Math.abs(value) >= 1000 ? WHOLE_FORMATTER : FORMATTER).format(value);
}
