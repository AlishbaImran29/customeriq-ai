"use client";

import { useEffect, useId, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Plus, UserCheck, UserPlus, X } from "lucide-react";
import { ChannelLabel } from "@/components/channel-icon";
import { CourierSuggestionNote } from "@/components/courier-suggestion";
import { Button } from "@/components/ui/button";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/config";
import { createQuickOrder, lookupCustomer, type CustomerLookup, type QuickOrderResponse } from "@/lib/api/orders";
import { getShipmentSummary } from "@/lib/api/shipments";
import {
  CHANNELS, PAYMENT_TYPES, PK_CITIES, PLATFORM_SUGGESTIONS, addProduct, addProducts, firstError, loadLastUsed, localToday,
  parseAmount, saveLastUsed, validate, type FieldErrors, type FieldName, type FormValues,
} from "@/lib/quick-order";
import { formatDate } from "@/lib/utils";
import { fmt } from "@/lib/format";

const textareaClass =
  "w-full rounded-xl border border-line bg-surface-2 px-3 py-2 text-base text-ink placeholder:text-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40";
const bigInput = "h-12 text-base";

/** A labelled field with its error underneath (an icon and words, never colour alone). */
export function Field({
  id, label, error, hint, children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-ink-2">
        {label}
      </label>
      {children}
      {hint}
      {error ? (
        <p id={`${id}-error`} role="alert" className="flex items-start gap-1.5 text-sm text-danger">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : null}
    </div>
  );
}

const blank = (today: string): FormValues => ({
  phone: "", customerName: "", city: "", courier: "", products: [], productInput: "", amount: "", paymentType: "", channel: "",
  platform: "", orderDate: today, note: "",
});

/**
 * Add one order by hand (about ten seconds on a phone). Mobile first: one column, large fields, the
 * phone number first, because typing it tells the seller whether this is a returning customer.
 */
export function QuickOrderForm() {
  const uid = useId();
  const id = (name: FieldName) => `${uid}-${name}`;
  const productId = `${uid}-productInput`; // the products field is a list, so its box has its own id

  const [today] = useState(() => localToday());
  const [values, setValues] = useState<FormValues>(() => blank(today));
  const [errors, setErrors] = useState<FieldErrors>({});
  const [topError, setTopError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [whatsappOk, setWhatsappOk] = useState(false);
  const [saved, setSaved] = useState<QuickOrderResponse | null>(null);
  const [lastProducts, setLastProducts] = useState<string[]>([]);
  const [lookup, setLookup] = useState<{ phone: string; result: CustomerLookup } | null>(null);
  const [prefilled, setPrefilled] = useState(false);
  const phoneRef = useRef<HTMLInputElement>(null);
  // Courier names offered while typing: the standard list plus any courier already in the data.
  const [couriers, setCouriers] = useState<string[]>([]);

  // Start with the channel, payment type and products used last on this device.
  useEffect(() => {
    const last = loadLastUsed(window.localStorage);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setValues((v) => ({ ...v, channel: last.channel, platform: last.platform, courier: last.courier, paymentType: last.paymentType }));
    setLastProducts(last.products);
    getShipmentSummary()
      .then((s) => setCouriers(s.couriers))
      .catch(() => undefined); // The suggestions are a convenience; any courier name can still be typed.
  }, []);

  // While the phone number is typed, ask the server whether it already belongs to a customer.
  const digits = values.phone.replace(/\D/g, "");
  useEffect(() => {
    if (digits.length < 10) return;
    const controller = new AbortController();
    const typed = values.phone;
    const timer = window.setTimeout(() => {
      lookupCustomer(typed, controller.signal)
        .then((result) => {
          setLookup({ phone: typed, result });
          if (result.found) {
            // Fill the name and city only where nothing has been typed yet.
            setValues((v) => {
              const name = v.customerName || result.name || "";
              const city = v.city || result.lastCity || "";
              if (name !== v.customerName || city !== v.city) setPrefilled(true);
              return { ...v, customerName: name, city };
            });
          }
        })
        .catch(() => undefined); // The hint is a convenience: the server checks the number again on Save.
    }, 350);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [values.phone, digits.length]);
  const known = lookup && digits.length >= 10 && lookup.phone === values.phone ? lookup.result : null;

  function change<K extends keyof FormValues>(name: K, value: FormValues[K]) {
    setValues((v) => ({ ...v, [name]: value }));
    setErrors((e) => ({ ...e, [name === "productInput" ? "products" : name]: undefined }));
    setSaved(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setTopError(null);
    const found = validate(values, today);
    if (Object.keys(found).length > 0) {
      setErrors(found);
      const first = firstError(found);
      if (first) document.getElementById(first === "products" ? productId : id(first))?.focus();
      return;
    }
    // Text still sitting in the product box is added, so it is not lost.
    const products = addProducts(values.products, values.productInput);
    setSaving(true);
    try {
      const response = await createQuickOrder({
        customerName: values.customerName.trim(), phone: values.phone.trim(), city: values.city.trim(), products,
        amount: parseAmount(values.amount) ?? 0, paymentType: values.paymentType, channel: values.channel,
        platform: values.channel === "other" ? values.platform.trim() : "",
        courier: values.courier.trim(),
        orderDate: values.orderDate, note: values.note.trim() || null,
        whatsappOk: whatsappOk || undefined,
      });
      saveLastUsed(window.localStorage, {
        channel: values.channel, platform: values.platform.trim(), courier: values.courier.trim(), paymentType: values.paymentType, products,
      });
      setLastProducts(products);
      setWhatsappOk(false);
      setSaved(response);
      setErrors({});
      setLookup(null);
      setPrefilled(false);
      // Ready for the next order: the phone, name, city, amount and note start empty again;
      // the channel, payment type, products and date stay.
      setValues((v) => ({ ...blank(today), channel: v.channel, platform: v.platform, courier: v.courier, paymentType: v.paymentType, products, orderDate: v.orderDate }));
      phoneRef.current?.focus();
    } catch (error) {
      const fields = (error instanceof ApiError ? (error.details as { fields?: FieldErrors } | undefined)?.fields : undefined);
      if (fields) {
        setErrors(fields);
        setTopError("Some fields need attention.");
      } else {
        setTopError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      }
    } finally {
      setSaving(false);
    }
  }

  const productsError = errors.products;
  return (
    <form onSubmit={submit} noValidate className="mx-auto max-w-xl space-y-5">
      <div aria-live="polite">
        {saved ? (
          <div className="flex items-start gap-2 rounded-xl border border-success/30 bg-success/10 px-3 py-3 text-sm text-success">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
            <p>
              <strong>{fmt("Order {id} saved for {name}.", { id: saved.orderId, name: saved.customerName })}</strong>{" "}
              {saved.returning
                ? fmt("Returning customer: {count} orders in total.", { count: saved.customerOrders })
                : "New customer added."}
            </p>
          </div>
        ) : null}
        {topError ? (
          <p role="alert" className="flex items-start gap-2 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            {topError}
          </p>
        ) : null}
      </div>

      <Field
        id={id("phone")}
        label="Phone number"
        error={errors.phone}
        hint={
          known ? (
            known.found ? (
              <p className="flex items-start gap-1.5 text-sm text-success">
                <UserCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>
                  {known.orders === 1
                    ? "Returning customer: 1 past order"
                    : fmt("Returning customer: {count} past orders", { count: known.orders })}
                  {known.lastOrderDate ? ` · ${fmt("Last order: {date}", { date: formatDate(known.lastOrderDate) })}` : ""}
                </span>
              </p>
            ) : known.valid ? (
              <p className="flex items-center gap-1.5 text-sm text-muted">
                <UserPlus className="h-4 w-4 shrink-0" aria-hidden="true" />
                New customer
              </p>
            ) : (
              <p className="text-sm text-muted">Enter a Pakistani mobile number, like 0300 1234567.</p>
            )
          ) : null
        }
      >
        <Input
          ref={phoneRef}
          id={id("phone")}
          type="tel"
          inputMode="tel"
          autoComplete="off"
          placeholder="0300 1234567"
          value={values.phone}
          onChange={(e) => {
            setPrefilled(false);
            change("phone", e.target.value);
          }}
          aria-invalid={errors.phone ? true : undefined}
          aria-describedby={errors.phone ? `${id("phone")}-error` : undefined}
          className={bigInput}
        />
      </Field>

      <Field
        id={id("customerName")}
        label="Customer name"
        error={errors.customerName}
        hint={prefilled ? <p className="text-xs text-muted">Name and city were filled in from their last order.</p> : null}
      >
        <Input
          id={id("customerName")}
          autoComplete="off"
          value={values.customerName}
          onChange={(e) => change("customerName", e.target.value)}
          aria-invalid={errors.customerName ? true : undefined}
          aria-describedby={errors.customerName ? `${id("customerName")}-error` : undefined}
          className={bigInput}
        />
      </Field>

      <Field id={id("city")} label="City" error={errors.city}>
        <Input
          id={id("city")}
          list={`${uid}-cities`}
          autoComplete="off"
          value={values.city}
          onChange={(e) => change("city", e.target.value)}
          aria-invalid={errors.city ? true : undefined}
          aria-describedby={errors.city ? `${id("city")}-error` : undefined}
          className={bigInput}
        />
        <datalist id={`${uid}-cities`}>
          {PK_CITIES.map((city) => (
            <option key={city} value={city} />
          ))}
        </datalist>
      </Field>

      <Field id={id("courier")} label="Courier (optional)" error={errors.courier}>
        <Input
          id={id("courier")}
          list={`${uid}-couriers`}
          autoComplete="off"
          placeholder="For example TCS, Leopards or Trax"
          value={values.courier}
          onChange={(e) => change("courier", e.target.value)}
          aria-invalid={errors.courier ? true : undefined}
          aria-describedby={errors.courier ? `${id("courier")}-error` : undefined}
          className={bigInput}
        />
        <datalist id={`${uid}-couriers`}>
          {couriers.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <CourierSuggestionNote city={values.city} onPick={(name) => change("courier", name)} />
      </Field>

      <Field id={productId} label="Products" error={productsError}>
        {values.products.length > 0 ? (
          <ul className="flex flex-wrap gap-2" aria-label="Products">
            {values.products.map((product) => (
              <li key={product} className="inline-flex items-center gap-1 rounded-full border border-line bg-surface-3 py-1 pl-3 pr-1 text-sm text-ink">
                {product}
                <button
                  type="button"
                  aria-label={fmt("Remove {product}", { product })}
                  className="rounded-full p-1.5 text-muted hover:bg-surface-2 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                  onClick={() => change("products", values.products.filter((p) => p !== product))}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <div className="flex gap-2">
          <Input
            id={productId}
            autoComplete="off"
            placeholder="Type a product and press Enter"
            value={values.productInput}
            onChange={(e) => change("productInput", e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                setValues((v) => ({ ...v, products: addProducts(v.products, v.productInput), productInput: "" }));
              }
            }}
            aria-invalid={productsError ? true : undefined}
            aria-describedby={productsError ? `${productId}-error` : undefined}
            className={bigInput}
          />
          <Button
            type="button"
            variant="secondary"
            className="h-12 shrink-0"
            onClick={() => setValues((v) => ({ ...v, products: addProduct(v.products, v.productInput), productInput: "" }))}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add
          </Button>
        </div>
        {values.products.length === 0 && lastProducts.length > 0 ? (
          <button
            type="button"
            className="text-sm text-accent underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
            onClick={() => change("products", lastProducts)}
          >
            Use last products: {lastProducts.join(", ")}
          </button>
        ) : null}
      </Field>

      <Field id={id("amount")} label="Amount (PKR)" error={errors.amount}>
        <Input
          id={id("amount")}
          inputMode="decimal"
          autoComplete="off"
          placeholder="2500"
          value={values.amount}
          onChange={(e) => change("amount", e.target.value)}
          aria-invalid={errors.amount ? true : undefined}
          aria-describedby={errors.amount ? `${id("amount")}-error` : undefined}
          className={bigInput}
        />
      </Field>

      <Field id={id("paymentType")} label="Payment" error={errors.paymentType}>
        <FilterPills
          label="Payment"
          options={PAYMENT_TYPES.map((p) => ({ value: p.value, label: p.label }))}
          value={values.paymentType as "cod" | "prepaid"}
          onChange={(value) => change("paymentType", value)}
        />
      </Field>

      <Field id={id("channel")} label="Where did the order come from?" error={errors.channel}>
        <FilterPills
          label="Where did the order come from?"
          options={CHANNELS.map((c) => ({
            value: c.value,
            label: <ChannelLabel channel={c.value}>{c.value === "other" ? "Other" : c.label}</ChannelLabel>,
          }))}
          value={values.channel as "instagram"}
          onChange={(value) => {
            change("channel", value);
            // "Other" opens a box for the platform's name: put the cursor in it.
            if (value === "other") window.setTimeout(() => document.getElementById(id("platform"))?.focus(), 50);
          }}
        />
      </Field>

      {values.channel === "other" ? (
        <Field id={id("platform")} label="Which platform? (optional)" error={errors.platform}>
          <Input
            id={id("platform")}
            list={`${uid}-platforms`}
            autoComplete="off"
            placeholder="For example TikTok, Daraz or walk-in"
            value={values.platform}
            onChange={(e) => change("platform", e.target.value)}
            aria-invalid={errors.platform ? true : undefined}
            aria-describedby={errors.platform ? `${id("platform")}-error` : undefined}
            className={bigInput}
          />
          <datalist id={`${uid}-platforms`}>
            {PLATFORM_SUGGESTIONS.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </Field>
      ) : null}

      <Field id={id("orderDate")} label="Date" error={errors.orderDate}>
        <Input
          id={id("orderDate")}
          type="date"
          max={today}
          value={values.orderDate}
          onChange={(e) => change("orderDate", e.target.value)}
          aria-invalid={errors.orderDate ? true : undefined}
          aria-describedby={errors.orderDate ? `${id("orderDate")}-error` : undefined}
          className={bigInput}
        />
      </Field>

      <label className="flex items-start gap-2 text-sm text-ink-2">
        <input type="checkbox" checked={whatsappOk} onChange={(e) => setWhatsappOk(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--color-accent)]" />
        The customer agreed to get order updates on WhatsApp
      </label>

      <Field id={id("note")} label="Note (optional)" error={errors.note}>
        <textarea
          id={id("note")}
          rows={2}
          value={values.note}
          onChange={(e) => change("note", e.target.value)}
          aria-invalid={errors.note ? true : undefined}
          aria-describedby={errors.note ? `${id("note")}-error` : undefined}
          className={textareaClass}
        />
      </Field>

      <Button type="submit" disabled={saving} className="h-12 w-full text-base">
        {saving ? <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" /> : null}
        {saving ? "Saving…" : "Save order"}
      </Button>
    </form>
  );
}
