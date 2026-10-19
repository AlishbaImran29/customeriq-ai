// Run with: npm test
import assert from "node:assert/strict";
import { test } from "node:test";
import { accept, acceptedRows, counts, reject, reopen, rowFrom, toAccepted, type ReviewCandidate, type ReviewRow } from "./chat-review.ts";

const TODAY = "2026-10-20";
const found: ReviewCandidate = {
  id: 0, customerName: "Ayesha", phone: "+923001234567", city: "Lahore", amount: 4500, paymentType: "cod",
  orderDate: "2026-10-18", orderTime: "2026-10-18T21:15:00",
};
const withProducts = (row: ReviewRow, products: string[]): ReviewRow => ({ ...row, values: { ...row.values, products } });

test("a suggested order becomes editable values, and products are never guessed", () => {
  const row = rowFrom(found);
  assert.equal(row.status, "pending");
  assert.deepEqual(row.values.products, []);
  assert.deepEqual([row.values.customerName, row.values.phone, row.values.city, row.values.amount, row.values.paymentType], ["Ayesha", "+923001234567", "Lahore", "4500", "cod"]);
});

test("missing facts stay empty for the seller to fill in", () => {
  const row = rowFrom({ ...found, customerName: "", phone: null, city: null, amount: null, paymentType: null });
  assert.deepEqual([row.values.customerName, row.values.phone, row.values.city, row.values.amount, row.values.paymentType], ["", "", "", "", ""]);
});

test("nothing is accepted until the seller has typed the products", () => {
  const blocked = accept(rowFrom(found), TODAY);
  assert.equal(blocked.status, "pending");
  assert.equal(blocked.errors.products, "Add at least one product.");
  assert.equal(accept(withProducts(rowFrom(found), ["Lawn suit"]), TODAY).status, "accepted");
});

test("a row with a missing phone, amount or payment is not accepted either", () => {
  const sparse = withProducts(rowFrom({ ...found, phone: null, amount: null, paymentType: null }), ["Kurta"]);
  const result = accept(sparse, TODAY);
  assert.equal(result.status, "pending");
  assert.deepEqual(Object.keys(result.errors).sort(), ["amount", "paymentType", "phone"]);
});

test("text still waiting in the product box counts as a product", () => {
  const row = { ...rowFrom(found), values: { ...rowFrom(found).values, productInput: "Dupatta" } };
  assert.equal(accept(row, TODAY).status, "accepted");
  assert.deepEqual(toAccepted(row).products, ["Dupatta"]);
});

test("a date in the future is refused", () => {
  const row = withProducts(rowFrom({ ...found, orderDate: "2026-12-01" }), ["Kurta"]);
  assert.equal(accept(row, TODAY).errors.orderDate, "The date is in the future.");
});

test("reject and reopen change only the status", () => {
  const row = withProducts(rowFrom(found), ["Lawn suit"]);
  const rejected = reject(accept(row, TODAY));
  assert.equal(rejected.status, "rejected");
  assert.equal(reopen(rejected).status, "pending");
  assert.deepEqual(reopen(rejected).values, row.values);
});

test("what is saved has only order fields, no chat text and no extra keys", () => {
  const accepted = toAccepted(withProducts(rowFrom(found), ["Lawn suit", "Dupatta"]));
  assert.deepEqual(accepted, {
    customerName: "Ayesha", phone: "+923001234567", city: "Lahore", products: ["Lawn suit", "Dupatta"], amount: 4500,
    paymentType: "cod", orderDate: "2026-10-18", messageTime: "2026-10-18T21:15:00",
  });
});

test("only accepted rows are saved, and the counts add up", () => {
  const a = accept(withProducts(rowFrom(found), ["A"]), TODAY);
  const b = reject(rowFrom({ ...found, id: 1 }));
  const c = rowFrom({ ...found, id: 2 });
  assert.deepEqual(counts([a, b, c]), { pending: 1, accepted: 1, rejected: 1 });
  assert.equal(acceptedRows([a, b, c]).length, 1);
});
