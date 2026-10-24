import assert from "node:assert/strict";
import { test } from "node:test";
import { eventLabel, percentText, pointsText, reasonPhrase } from "./messenger-text.ts";

test("every recorded reason code becomes a plain sentence", () => {
  assert.equal(reasonPhrase("no_consent")?.text, "The customer has not agreed to be messaged.");
  assert.equal(reasonPhrase("weekly_cap")?.text, "The weekly limit of marketing messages was reached.");
  assert.equal(reasonPhrase(null), null);
  assert.equal(reasonPhrase(""), null);
});

test("codes with a value in them keep the value as a parameter", () => {
  assert.deepEqual(reasonPhrase("missing_variable:order_number"), { text: "A value is missing: {name}.", params: { name: "order_number" } });
  assert.deepEqual(reasonPhrase("whatsapp_131026"), { text: "WhatsApp refused it (code {code}).", params: { code: "131026" } });
  assert.deepEqual(reasonPhrase("email_something_new"), { text: "The email could not be sent ({code}).", params: { code: "something_new" } });
});

test("an unknown code is shown, never hidden", () => {
  assert.deepEqual(reasonPhrase("brand_new_code"), { text: "Reason: {code}.", params: { code: "brand_new_code" } });
});

test("event names are readable", () => {
  assert.equal(eventLabel("order_out_for_delivery"), "Order out for delivery");
  assert.equal(eventLabel("campaign_12"), "Product announcement");
  assert.equal(eventLabel("journey_at_risk_1"), "At-Risk: win-back");
  assert.equal(eventLabel(null), "Other");
  assert.equal(eventLabel("my_own_event"), "my_own_event");
});

test("shares and gaps are formatted for people", () => {
  assert.equal(percentText(0.1234), "12.3%");
  assert.equal(percentText(0.5, 0), "50%");
  assert.equal(percentText(null), "-");
  assert.equal(pointsText(0.14), "+14.0");
  assert.equal(pointsText(-0.025), "-2.5");
  assert.equal(pointsText(undefined), "-");
});
