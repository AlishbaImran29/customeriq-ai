// Every amount in the app is shown in Pakistani rupees ("Rs. 3,500"), the same way the customer emails and WhatsApp messages
// write prices. Amounts are shown exactly as stored: there is no exchange rate and no currency choice.
// (The public Online Retail II test dataset is in pounds; its numbers are shown unchanged, only the label is Rs.)

const WHOLE = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const CENTS = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const COMPACT = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

/** Rs. 1,234 for large amounts and whole numbers, Rs. 12.50 for small amounts with paisa, Rs. 1.2M when compact. */
export function formatMoney(value: number, compact = false): string {
  const sign = value < 0 ? "-" : "";
  const amount = Math.abs(value);
  if (compact) return `${sign}Rs. ${COMPACT.format(amount)}`;
  const whole = amount >= 1000 || Number.isInteger(amount);
  return `${sign}Rs. ${(whole ? WHOLE : CENTS).format(amount)}`;
}
