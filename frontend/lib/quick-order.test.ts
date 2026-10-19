// Run with: npm test
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  addProduct, addProducts, firstError, loadLastUsed, localToday, parseAmount, saveLastUsed, validate,
  LAST_USED_KEY, type FormValues,
} from "./quick-order.ts";

const TODAY = "2026-10-20";
const good = (changes: Partial<FormValues> = {}): FormValues => ({
  phone: "0300-1234567", customerName: "Ayesha Khan", city: "Lahore", courier: "", products: ["Red lawn suit"], productInput: "",
  amount: "4500", paymentType: "cod", channel: "instagram", platform: "", orderDate: TODAY, note: "", ...changes,
});

test("a complete form has no problems", () => {
  assert.deepEqual(validate(good(), TODAY), {});
});

test("an empty form reports every field at once, in the order the form shows them", () => {
  const empty = good({ phone: "", customerName: "", city: "", products: [], amount: "", paymentType: "", channel: "" });
  const errors = validate(empty, TODAY);
  assert.deepEqual(Object.keys(errors).sort(), ["amount", "channel", "city", "customerName", "paymentType", "phone", "products"]);
  assert.equal(firstError(errors), "phone");
  assert.equal(firstError({}), null);
});

test("text still waiting in the product box counts as a product", () => {
  assert.equal(validate(good({ products: [], productInput: "Dupatta" }), TODAY).products, undefined);
  assert.equal(validate(good({ products: [], productInput: "  " }), TODAY).products, "Add at least one product.");
});

test("amounts: commas are fine, nonsense is not", () => {
  assert.equal(parseAmount("2,500"), 2500);
  assert.equal(parseAmount(" 99.5 "), 99.5);
  for (const bad of ["", "abc", "12abc", "1.2.3", "-5", "1e3", "Rs 500"]) assert.equal(parseAmount(bad), null, bad);
  assert.equal(validate(good({ amount: "abc" }), TODAY).amount, "Enter the amount as a number, like 2500.");
  assert.equal(validate(good({ amount: "0" }), TODAY).amount, "The amount must be more than 0.");
  assert.equal(validate(good({ amount: "20000000" }), TODAY).amount, "The amount is too large.");
});

test("the date cannot be in the future", () => {
  assert.equal(validate(good({ orderDate: "2026-10-21" }), TODAY).orderDate, "The date is in the future.");
  assert.equal(validate(good({ orderDate: "20/10/2026" }), TODAY).orderDate, "Enter the date as YYYY-MM-DD.");
  assert.equal(validate(good({ orderDate: "2026-09-01" }), TODAY).orderDate, undefined);
});

test("products are trimmed, never repeated, and can be pasted several at a time", () => {
  assert.deepEqual(addProduct([], "  Kurta   set "), ["Kurta set"]);
  assert.deepEqual(addProduct(["Kurta"], "kurta"), ["Kurta"]);
  assert.deepEqual(addProduct(["Kurta"], "   "), ["Kurta"]);
  assert.deepEqual(addProducts(["Kurta"], "Scarf, kurta,\nBag,, "), ["Kurta", "Scarf", "Bag"]);
  const many = Array.from({ length: 21 }, (_, i) => `P${i}`);
  assert.equal(validate(good({ products: many }), TODAY).products, "Add at most 20 products.");
});

test("the last used channel, payment and products are remembered and survive bad data", () => {
  const store = new Map<string, string>();
  const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
  assert.deepEqual(loadLastUsed(storage), { channel: "", platform: "", courier: "", paymentType: "", products: [] });
  saveLastUsed(storage, { channel: "whatsapp", platform: "", courier: "", paymentType: "prepaid", products: ["Kurta", "Scarf"] });
  assert.deepEqual(loadLastUsed(storage), { channel: "whatsapp", platform: "", courier: "", paymentType: "prepaid", products: ["Kurta", "Scarf"] });
  saveLastUsed(storage, { channel: "other", platform: " TikTok ", courier: " TCS ", paymentType: "cod", products: [] });
  assert.equal(loadLastUsed(storage).platform, "TikTok");
  assert.equal(loadLastUsed(storage).courier, "TCS");

  store.set(LAST_USED_KEY, JSON.stringify({ channel: "tiktok", paymentType: "cash", products: ["ok", 5, "", null] }));
  assert.deepEqual(loadLastUsed(storage), { channel: "", platform: "", courier: "", paymentType: "", products: ["ok"] });
  store.set(LAST_USED_KEY, "not json");
  assert.deepEqual(loadLastUsed(storage), { channel: "", platform: "", courier: "", paymentType: "", products: [] });
  const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.deepEqual(loadLastUsed(broken), { channel: "", platform: "", courier: "", paymentType: "", products: [] });
  saveLastUsed(broken, { channel: "", platform: "", courier: "", paymentType: "", products: [] });   // must not throw
});

test("today is the date on the seller's own device", () => {
  assert.equal(localToday(new Date(2026, 9, 5, 23, 59)), "2026-10-05");
  assert.equal(localToday(new Date(2026, 0, 1, 0, 1)), "2026-01-01");
});

test("the platform name only matters for Other, and is length limited", () => {
  assert.equal(validate(good({ channel: "other", platform: "TikTok" }), TODAY).platform, undefined);
  assert.equal(validate(good({ channel: "other", platform: "x".repeat(51) }), TODAY).platform, "The platform name is too long (50 characters at most).");
  assert.equal(validate(good({ channel: "instagram", platform: "x".repeat(51) }), TODAY).platform, undefined);
});

test("the courier is optional and length limited", () => {
  assert.equal(validate(good({ courier: "" }), TODAY).courier, undefined);
  assert.equal(validate(good({ courier: "TCS" }), TODAY).courier, undefined);
  assert.equal(validate(good({ courier: "x".repeat(61) }), TODAY).courier, "The courier name is too long (60 characters at most).");
});
