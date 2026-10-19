// Run with: npm test
import assert from "node:assert/strict";
import { test } from "node:test";
import { whatsappLink, whatsappMessage } from "./whatsapp.ts";

test("the message names the order and the amount, in English and in Urdu", () => {
  const en = whatsappMessage("en", "PUB-548169", "£120.50");
  assert.ok(en.includes("PUB-548169") && en.includes("£120.50") && en.includes("YES"));
  const ur = whatsappMessage("ur", "PUB-548169", "£120.50");
  assert.ok(ur.includes("PUB-548169") && ur.includes("£120.50") && ur.includes("ہاں"));
  assert.notEqual(en, ur);
});

test("the link opens the right chat with the message already typed", () => {
  const link = whatsappLink("923001234567", "en", "A&B 1", "$10");
  assert.ok(link);
  const url = new URL(link);
  assert.equal(url.origin + url.pathname, "https://wa.me/923001234567");
  // Characters like & and spaces survive the round trip, so the message cannot be cut short.
  assert.equal(url.searchParams.get("text"), whatsappMessage("en", "A&B 1", "$10"));
});

test("Urdu text is encoded and decodes back unchanged", () => {
  const link = whatsappLink("923001234567", "ur", "O1", "Rs 500");
  assert.ok(link);
  assert.equal(new URL(link).searchParams.get("text"), whatsappMessage("ur", "O1", "Rs 500"));
});

test("no phone, or a phone that is not international digits, gives no link", () => {
  for (const bad of [null, undefined, "", "0300 1234567", "+923001234567", "03001234567", "12345", "92300ABC4567", "9".repeat(16)]) {
    assert.equal(whatsappLink(bad, "en", "O1", "$1"), null, String(bad));
  }
});
