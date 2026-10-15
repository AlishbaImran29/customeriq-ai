"use client";

import { useEffect, useSyncExternalStore } from "react";
import { EXTRA } from "@/lib/translations";

// Interface language. English is the source text; Urdu is looked up by the exact English
// string, so anything without a translation simply stays in English (never blank).
// The page layout stays left-to-right; only the words change.

export const LANGUAGES = [
  { code: "en", name: "English" },
  { code: "ur", name: "اردو" },
  { code: "hi", name: "हिन्दी" },
  { code: "bn", name: "বাংলা" },
  { code: "ar", name: "العربية" },
  { code: "es", name: "Español" },
  { code: "fr", name: "Français" },
  { code: "de", name: "Deutsch" },
  { code: "pt", name: "Português" },
  { code: "zh", name: "中文" },
  { code: "ru", name: "Русский" },
  { code: "id", name: "Bahasa Indonesia" },
] as const;

export type Language = (typeof LANGUAGES)[number]["code"];

function isLanguage(value: unknown): value is Language {
  return LANGUAGES.some((l) => l.code === value);
}

const STORAGE_KEY = "ciq_language";

export const URDU: Record<string, string> = {
  // Navigation
  Insights: "بصیرت",
  Actions: "اقدامات",
  Data: "ڈیٹا",
  Overview: "جائزہ",
  Segmentation: "کسٹمر گروپس",
  "Churn Prediction": "کسٹمر چھوڑنے کی پیش گوئی",
  "Lifetime Value": "مجموعی قدر",
  "Health Scores": "صحت کے اسکور",
  "Revenue Intelligence": "آمدنی کا تجزیہ",
  Recommendations: "سفارشات",
  "AI Business Assistant": "اے آئی بزنس اسسٹنٹ",
  "Import Data": "ڈیٹا درآمد کریں",
  "Skip to content": "مواد پر جائیں",
  "E-commerce growth copilot for Shopify, WooCommerce, and Magento":
    "شاپیفائی، ووکامرس اور میجنٹو کے لیے ای کامرس گروتھ معاون",
  "Live data": "لائیو ڈیٹا",
  "Demo data": "ڈیمو ڈیٹا",
  "Live workspace": "لائیو ورک اسپیس",
  "Demo workspace": "ڈیمو ورک اسپیس",
  "Dashboards use your imported data. Predictions appear only when a model passed its accuracy test.":
    "ڈیش بورڈ آپ کا درآمد کردہ ڈیٹا استعمال کرتے ہیں۔ پیش گوئیاں صرف تب دکھائی جاتی ہیں جب ماڈل درستگی کا امتحان پاس کر لے۔",
  "No backend configured. Dashboards show sample data.": "بیک اینڈ سیٹ نہیں ہے۔ ڈیش بورڈ نمونے کا ڈیٹا دکھا رہے ہیں۔",
  "Sign out": "سائن آؤٹ",

  // Page titles and descriptions
  "Customer Intelligence Dashboard": "کسٹمر انٹیلی جنس ڈیش بورڈ",
  "Customer performance and business health at a glance: segmentation, churn risk, lifetime value, and growth opportunities.":
    "کسٹمرز کی کارکردگی اور کاروبار کی صحت ایک نظر میں: گروپس، چھوڑنے کا خطرہ، مجموعی قدر اور ترقی کے مواقع۔",
  "Customer Segmentation": "کسٹمر گروپس",
  "Customers grouped by recency, frequency, and spend (RFM) into Champions, Loyal Customers, Potential Loyalists, At-Risk Customers, and Lost Customers.":
    "کسٹمرز کو حالیہ خریداری، خریداری کی تعداد اور خرچ (RFM) کی بنیاد پر چیمپئنز، وفادار، ممکنہ وفادار، خطرے والے اور کھوئے ہوئے کسٹمرز میں تقسیم کیا گیا ہے۔",
  "Which customers are likely to stop purchasing, with churn probability, risk level, and a recommended action for each.":
    "کون سے کسٹمرز خریداری چھوڑ سکتے ہیں، ان کے چھوڑنے کا امکان، خطرے کی سطح اور ہر ایک کے لیے تجویز کردہ اقدام۔",
  "Customer Lifetime Value": "کسٹمر کی مجموعی قدر",
  "Customer value to date, with predicted CLV and growth potential for every customer and segment.":
    "اب تک کی کسٹمر قدر، ہر کسٹمر اور گروپ کے لیے پیش گوئی شدہ قدر اور ترقی کی گنجائش۔",
  "Customer Health Score": "کسٹمر ہیلتھ اسکور",
  "A 0–100 score combining purchase frequency, spending behavior, customer engagement, and activity trends.":
    "۰ سے ۱۰۰ کا اسکور جو خریداری کی تعداد، خرچ کے انداز، کسٹمر کی دلچسپی اور سرگرمی کے رجحانات کو ملاتا ہے۔",
  "Revenue trends, forecasting, revenue drivers, and revenue-at-risk analysis for growth decisions.":
    "آمدنی کے رجحانات، پیش گوئی، آمدنی بڑھانے والے عوامل اور خطرے میں آمدنی کا تجزیہ۔",
  "AI Recommendations": "اے آئی سفارشات",
  "Next best actions for retention campaigns, upsell, cross-sell, and customer recovery, ranked by impact.":
    "کسٹمرز کو روکنے، زیادہ بیچنے اور کھوئے ہوئے کسٹمرز کو واپس لانے کے بہترین اگلے اقدامات، اثر کے لحاظ سے ترتیب وار۔",
  "Import Customer Data": "کسٹمر ڈیٹا درآمد کریں",
  "Upload customer and order history from a CSV or Excel export to power segmentation, churn, and CLV analysis.":
    "گروپس، چھوڑنے اور مجموعی قدر کے تجزیے کے لیے CSV یا Excel فائل سے کسٹمر اور آرڈر کی تاریخ اپ لوڈ کریں۔",
  "Ask questions about your customers in plain language, such as who is going inactive, why revenue moved, or which segment is most valuable.":
    "اپنے کسٹمرز کے بارے میں آسان زبان میں سوال پوچھیں، جیسے کون غیر فعال ہو رہا ہے، آمدنی کیوں بدلی، یا کون سا گروپ سب سے قیمتی ہے۔",
  Account: "اکاؤنٹ",
  "Your sign-in details and password.": "آپ کے سائن اِن کی تفصیل اور پاس ورڈ۔",

  // Dashboard cards
  "Total Customers": "کل کسٹمرز",
  Revenue: "آمدنی",
  "Revenue (last 90 days)": "آمدنی (پچھلے ۹۰ دن)",
  "Customer Lifetime Value (to date)": "کسٹمر کی مجموعی قدر (اب تک)",
  "Retention Rate": "برقرار رہنے کی شرح",
  "Retention Rate (90 days)": "برقرار رہنے کی شرح (۹۰ دن)",
  "Churn Risk": "چھوڑنے کا خطرہ",
  "Predicted Churn Risk": "چھوڑنے کا پیش گوئی شدہ خطرہ",
  "Growth Score": "گروتھ اسکور",
  "Not available yet": "ابھی دستیاب نہیں",
  "Not available yet.": "ابھی دستیاب نہیں۔",
  "Not enough history to compare": "موازنے کے لیے کافی تاریخ نہیں",
  "vs last period": "پچھلے دور کے مقابلے میں",
  "No customer data yet": "ابھی کسٹمر ڈیٹا نہیں ہے",
  "Import a CSV or Excel file of orders to see this page with your own data.":
    "اس صفحے پر اپنا ڈیٹا دیکھنے کے لیے آرڈرز کی CSV یا Excel فائل درآمد کریں۔",
  "Import data": "ڈیٹا درآمد کریں",

  // Import page
  "Upload customer and order data": "کسٹمر اور آرڈر کا ڈیٹا اپ لوڈ کریں",
  "CSV template": "CSV نمونہ",
  "No file selected": "کوئی فائل منتخب نہیں",
  "Choose a file to check its columns and preview the rows before importing.":
    "درآمد سے پہلے کالم جانچنے اور قطاریں دیکھنے کے لیے فائل منتخب کریں۔",
  "Import customers": "کسٹمرز درآمد کریں",
  "Importing…": "درآمد ہو رہا ہے…",
  "Import complete": "درآمد مکمل",
  "Import failed": "درآمد ناکام",
  "Import another file": "ایک اور فائل درآمد کریں",
  "Choose another file": "دوسری فائل منتخب کریں",
  "Ready to import": "درآمد کے لیے تیار",
  Preview: "پیش منظر",
  "New orders": "نئے آرڈرز",
  "Updated orders": "اپ ڈیٹ شدہ آرڈرز",
  "Rejected rows": "مسترد قطاریں",
  "Rows received": "موصول قطاریں",
};

let current: Language = "en";
let started = false;
const listeners = new Set<() => void>();

function set(next: Language) {
  current = next;
  if (typeof document !== "undefined") document.documentElement.lang = next;
  listeners.forEach((listener) => listener());
}

function start() {
  if (started) return;
  started = true;
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (isLanguage(saved) && saved !== "en") set(saved);
  } catch {
    // Storage blocked: stay in English.
  }
}

export function setLanguage(next: Language) {
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // The choice just won't be remembered.
  }
  set(next);
}

export function translate(language: Language, text: string) {
  if (language === "en") return text;
  const table = language === "ur" ? URDU : EXTRA[language];
  // "Not available yet." and "Not available yet" share one translation.
  return table?.[text] ?? table?.[text.replace(/\.$/, "")] ?? text;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Server and first render are English, so hydration always matches. */
export function useLanguage() {
  const language = useSyncExternalStore(subscribe, () => current, () => "en" as Language);
  useEffect(start, []);
  return { language, t: (text: string) => translate(language, text) };
}
