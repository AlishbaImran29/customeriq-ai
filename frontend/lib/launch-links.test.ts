import assert from "node:assert/strict";
import { test } from "node:test";
import { adAsText, instagramAsText, parseHashtags, phoneDigits, waMeLink, wrapLines } from "./launch-links.ts";

// All names and numbers below are made up for the tests.

test("a vendor phone from the backend becomes wa.me digits", () => {
  assert.equal(phoneDigits("+923001234567"), "923001234567");
  assert.equal(phoneDigits(null), null);
  assert.equal(phoneDigits("12"), null);
});

test("the wa.me link has the message ready and is null without a number or message", () => {
  assert.equal(waMeLink("+923001234567", "Hello & welcome"), "https://wa.me/923001234567?text=Hello%20%26%20welcome");
  assert.equal(waMeLink(null, "Hello"), null);
  assert.equal(waMeLink("+923001234567", "   "), null);
});

test("an ad and an instagram post are copied as plain text", () => {
  assert.equal(adAsText({ hook: "H", primary_text: "P", headline: "T", cta: "Order Now" }), "H\n\nP\n\nT\nOrder Now");
  assert.equal(instagramAsText({ caption: "Hi", hashtags: ["#a", "#b"] }), "Hi\n\n#a #b");
  assert.equal(instagramAsText({ caption: "Hi", hashtags: [] }), "Hi");
});

test("hashtags are cleaned, prefixed and not repeated", () => {
  assert.deepEqual(parseHashtags("summer, #fan  ##cool fan! #summer"), ["#summer", "#fan", "#cool"]);
  assert.deepEqual(parseHashtags("   "), []);
});

test("text wraps between words and is cut with an ellipsis when too long", () => {
  assert.deepEqual(wrapLines("one two three four", 9, 5), ["one two", "three", "four"]);
  assert.deepEqual(wrapLines("averyveryverylongword", 5, 3), ["averyveryverylongword"]);
  assert.deepEqual(wrapLines("aa bb cc dd ee", 5, 2), ["aa bb", "cc dd…"]);
  assert.deepEqual(wrapLines("", 5, 2), []);
});
