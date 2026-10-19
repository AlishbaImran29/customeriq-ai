"use client";

import { useId } from "react";
import { Check, CheckCircle2, Pencil, Plus, Undo2, X, XCircle } from "lucide-react";
import { Field } from "@/components/quick-order-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FilterPills } from "@/components/ui/filter-pills";
import { Input } from "@/components/ui/input";
import type { Candidate } from "@/lib/api/whatsapp";
import { accept, reject, reopen, type ReviewRow, type RowValues } from "@/lib/chat-review";
import { useLanguage } from "@/lib/i18n";
import { PAYMENT_TYPES, PK_CITIES, addProduct, addProducts, type FieldName } from "@/lib/quick-order";
import { formatDate } from "@/lib/utils";

const CONFIDENCE_VARIANT = { high: "success", medium: "warning", low: "info" } as const;
const field = "h-11 text-base";

/** How sure the rules are, in words AND an icon (never colour alone). */
function ConfidenceBadge({ candidate }: { candidate: Candidate }) {
  const { t } = useLanguage();
  return <Badge variant={CONFIDENCE_VARIANT[candidate.confidence]}>{t(candidate.confidenceLabel)}</Badge>;
}

/** The original messages next to the order. They are shown here only and are never saved. */
function OriginalMessages({ candidate }: { candidate: Candidate }) {
  const { t } = useLanguage();
  return (
    <div>
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">
        {t("Original messages")} <span className="normal-case">({t("shown here only, never saved")})</span>
      </p>
      <ul className="max-h-56 space-y-2 overflow-y-auto rounded-xl border border-line bg-surface-2/60 p-3 text-sm">
        {candidate.messages.map((message, index) => (
          <li key={index}>
            <p className="text-xs text-muted">
              <strong className="text-ink-2">{message.sender}</strong> · {formatDate(message.time)}{" "}
              {new Date(message.time).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
            </p>
            <p className="whitespace-pre-wrap break-words text-ink-2">{message.text}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** One suggested order: check it against the messages, fix what is wrong, then accept or reject. */
export function ChatOrderCard({
  row,
  candidate,
  today,
  onChange,
}: {
  row: ReviewRow;
  candidate: Candidate;
  today: string;
  onChange: (row: ReviewRow) => void;
}) {
  const { t, tf } = useLanguage();
  const uid = useId();
  const id = (name: string) => `${uid}-${name}`;
  const v = row.values;
  const e = row.errors;

  function set<K extends keyof RowValues>(name: K, value: RowValues[K]) {
    const errorKey = (name === "productInput" ? "products" : name) as FieldName;
    onChange({ ...row, values: { ...v, [name]: value }, errors: { ...e, [errorKey]: undefined } });
  }
  const invalid = (name: FieldName) => (e[name] ? { "aria-invalid": true as const, "aria-describedby": `${id(name)}-error` } : {});

  const summary = (
    <p className="text-sm text-ink-2">
      <strong className="text-ink">{v.customerName || t("No name")}</strong> · {v.phone} · {v.city} · {v.amount}{" "}
      · {v.paymentType === "cod" ? "COD" : t("Prepaid")} · {formatDate(v.orderDate)}
      {v.products.length > 0 ? ` · ${v.products.join(", ")}` : ""}
    </p>
  );

  if (row.status === "accepted" || row.status === "rejected") {
    const isAccepted = row.status === "accepted";
    return (
      <li className="flex flex-col gap-3 rounded-xl border border-line bg-surface-2/40 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <p className={`flex items-center gap-1.5 text-sm font-medium ${isAccepted ? "text-success" : "text-muted"}`}>
            {isAccepted ? <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> : <XCircle className="h-4 w-4" aria-hidden="true" />}
            {isAccepted ? t("Accepted") : t("Rejected")}
          </p>
          {isAccepted ? summary : <p className="text-sm text-muted">{t("This order will not be saved.")}</p>}
        </div>
        <div className="flex shrink-0 gap-2">
          {isAccepted ? (
            <Button variant="secondary" onClick={() => onChange(reopen(row))}>
              <Pencil className="h-4 w-4" aria-hidden="true" />
              {t("Edit")}
            </Button>
          ) : (
            <Button variant="secondary" onClick={() => onChange(reopen(row))}>
              <Undo2 className="h-4 w-4" aria-hidden="true" />
              {t("Undo")}
            </Button>
          )}
        </div>
      </li>
    );
  }

  return (
    <li className="space-y-4 rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ConfidenceBadge candidate={candidate} />
        {candidate.otherAmounts.length > 0 ? (
          <p className="text-xs text-muted">
            {tf("Other amounts in this chat: {amounts}", { amounts: candidate.otherAmounts.join(", ") })}
          </p>
        ) : null}
      </div>

      <OriginalMessages candidate={candidate} />

      <div className="grid gap-4 sm:grid-cols-2">
        <Field id={id("phone")} label={t("Phone number")} error={e.phone}>
          <Input id={id("phone")} type="tel" inputMode="tel" value={v.phone} onChange={(x) => set("phone", x.target.value)} className={field} {...invalid("phone")} />
        </Field>
        <Field id={id("customerName")} label={t("Customer name")} error={e.customerName}>
          <Input id={id("customerName")} value={v.customerName} onChange={(x) => set("customerName", x.target.value)} className={field} {...invalid("customerName")} />
        </Field>
        <Field id={id("city")} label={t("City")} error={e.city}>
          <Input id={id("city")} list={`${uid}-cities`} value={v.city} onChange={(x) => set("city", x.target.value)} className={field} {...invalid("city")} />
          <datalist id={`${uid}-cities`}>
            {PK_CITIES.map((city) => (
              <option key={city} value={city} />
            ))}
          </datalist>
        </Field>
        <Field id={id("amount")} label={t("Amount (PKR)")} error={e.amount}>
          <Input id={id("amount")} inputMode="decimal" value={v.amount} onChange={(x) => set("amount", x.target.value)} className={field} {...invalid("amount")} />
        </Field>
      </div>

      <Field id={id("productInput")} label={t("Products (type them from the messages)")} error={e.products}>
        {v.products.length > 0 ? (
          <ul className="flex flex-wrap gap-2" aria-label={t("Products")}>
            {v.products.map((product) => (
              <li key={product} className="inline-flex items-center gap-1 rounded-full border border-line bg-surface-3 py-1 pl-3 pr-1 text-sm text-ink">
                {product}
                <button
                  type="button"
                  aria-label={tf("Remove {product}", { product })}
                  className="rounded-full p-1.5 text-muted hover:bg-surface-2 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
                  onClick={() => set("products", v.products.filter((p) => p !== product))}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <div className="flex gap-2">
          <Input
            id={id("productInput")}
            autoComplete="off"
            placeholder={t("Type a product and press Enter")}
            value={v.productInput}
            onChange={(x) => set("productInput", x.target.value)}
            onKeyDown={(x) => {
              if (x.key === "Enter") {
                x.preventDefault();
                onChange({ ...row, values: { ...v, products: addProducts(v.products, v.productInput), productInput: "" } });
              }
            }}
            className={field}
            {...(e.products ? { "aria-invalid": true as const, "aria-describedby": `${id("productInput")}-error` } : {})}
          />
          <Button
            type="button"
            variant="secondary"
            className="h-11 shrink-0"
            onClick={() => onChange({ ...row, values: { ...v, products: addProduct(v.products, v.productInput), productInput: "" } })}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t("Add")}
          </Button>
        </div>
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field id={id("paymentType")} label={t("Payment")} error={e.paymentType}>
          <FilterPills
            label={t("Payment")}
            options={PAYMENT_TYPES.map((p) => ({ value: p.value, label: t(p.label) }))}
            value={v.paymentType as "cod" | "prepaid"}
            onChange={(value) => set("paymentType", value)}
          />
        </Field>
        <Field id={id("orderDate")} label={t("Date")} error={e.orderDate}>
          <Input id={id("orderDate")} type="date" max={today} value={v.orderDate} onChange={(x) => set("orderDate", x.target.value)} className={field} {...invalid("orderDate")} />
        </Field>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button onClick={() => onChange(accept(row, today))}>
          <Check className="h-4 w-4" aria-hidden="true" />
          {t("Accept")}
        </Button>
        <Button variant="secondary" onClick={() => onChange(reject(row))}>
          <X className="h-4 w-4" aria-hidden="true" />
          {t("Reject")}
        </Button>
      </div>
    </li>
  );
}
