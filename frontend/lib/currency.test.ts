import assert from "node:assert/strict";
import test from "node:test";
import { formatMoney } from "./currency.ts";

test("money is shown as Rs. with thousands separators", () => {
  assert.equal(formatMoney(3500), "Rs. 3,500");
  assert.equal(formatMoney(1234567), "Rs. 1,234,567");
  assert.equal(formatMoney(12.5), "Rs. 12.50");
  assert.equal(formatMoney(500), "Rs. 500");
  assert.equal(formatMoney(-2500), "-Rs. 2,500");
  assert.equal(formatMoney(0), "Rs. 0");
});

test("compact money is short", () => {
  assert.equal(formatMoney(48200, true), "Rs. 48.2K");
  assert.equal(formatMoney(1500000, true), "Rs. 1.5M");
});
