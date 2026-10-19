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
  "Cohort Retention": "گروہ وار برقراری",
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

  // Order Risk: the "Why?" reasons. Words in {braces} are replaced by numbers or names.
  // These must match the templates in backend/app/services/order_risk_reasons.py.
  "Returned {returned} of {total} earlier orders": "{total} پچھلے آرڈرز میں سے {returned} واپس ہوئے",
  "New customer: no earlier orders to learn from": "نیا کسٹمر: سیکھنے کے لیے پچھلے آرڈرز موجود نہیں",
  "Has {total} earlier orders": "اس کسٹمر کے پچھلے آرڈرز: {total}",
  "Order value is {ratio}x this customer's usual": "آرڈر کی رقم اس کسٹمر کی عام رقم سے {ratio} گنا ہے",
  "Days since the previous order: {days} (fewer than usual)": "پچھلے آرڈر کو گزرے دن: {days} (معمول سے کم)",
  "Days since the previous order: {days} (more than usual)": "پچھلے آرڈر کو گزرے دن: {days} (معمول سے زیادہ)",
  "Number of items: {count} (more than usual)": "اشیاء کی تعداد: {count} (معمول سے زیادہ)",
  "Number of items: {count} (fewer than usual)": "اشیاء کی تعداد: {count} (معمول سے کم)",
  "Different products: {count} (more than usual)": "مختلف مصنوعات: {count} (معمول سے زیادہ)",
  "Different products: {count} (fewer than usual)": "مختلف مصنوعات: {count} (معمول سے کم)",
  "Placed around {hour}:00": "آرڈر تقریباً {hour}:00 بجے دیا گیا",
  "The address is shorter than usual ({characters} characters)": "پتہ معمول سے مختصر ہے ({characters} حروف)",
  "The address is longer than usual ({characters} characters)": "پتہ معمول سے طویل ہے ({characters} حروف)",
  "The address has no house number": "پتے میں مکان نمبر نہیں ہے",
  "No address was provided": "پتہ فراہم نہیں کیا گیا",
  "The phone number does not look valid": "فون نمبر درست نہیں لگتا",
  "No phone number was provided": "فون نمبر فراہم نہیں کیا گیا",
  "Orders from {country} are returned more often in past data": "ماضی کے ڈیٹا میں {country} کے آرڈرز زیادہ واپس ہوتے ہیں",
  "Placed on a Monday": "آرڈر پیر کے دن دیا گیا",
  "Placed on a Tuesday": "آرڈر منگل کے دن دیا گیا",
  "Placed on a Wednesday": "آرڈر بدھ کے دن دیا گیا",
  "Placed on a Thursday": "آرڈر جمعرات کے دن دیا گیا",
  "Placed on a Friday": "آرڈر جمعہ کے دن دیا گیا",
  "Placed on a Saturday": "آرڈر ہفتہ کے دن دیا گیا",
  "Placed on a Sunday": "آرڈر اتوار کے دن دیا گیا",
  // Order Risk: actions and the WhatsApp button. The three actions come from the backend
  // (RISK_ACTIONS in backend/app/services/order_risk_config.py) and must match it.
  "Ship normally": "عام طریقے سے بھیجیں",
  "Confirm on WhatsApp": "واٹس ایپ پر تصدیق کریں",
  "Ask for advance payment or call the customer": "ایڈوانس ادائیگی مانگیں یا کسٹمر کو کال کریں",
  "Message language": "پیغام کی زبان",
  "No usable phone number in the data for this customer, so WhatsApp cannot be opened.": "اس کسٹمر کا قابلِ استعمال فون نمبر ڈیٹا میں نہیں ہے، اس لیے واٹس ایپ نہیں کھل سکتا۔",
  "Some orders have no usable phone number in your data, so their WhatsApp button is disabled.": "کچھ آرڈرز کا قابلِ استعمال فون نمبر آپ کے ڈیٹا میں نہیں ہے، اس لیے ان کا واٹس ایپ بٹن بند ہے۔",
  "Opens WhatsApp with the message ready. Nothing is sent until you press send.": "واٹس ایپ پیغام کے ساتھ کھلتا ہے۔ جب تک آپ بھیجیں نہ دبائیں، کچھ نہیں بھیجا جاتا۔",
  // Order Risk page. Words in {braces} are replaced by numbers or names.
  "Order Risk": "آرڈر رسک",
  "Which recent orders are likely to be refused or returned, why, and what to do before shipping.": "کون سے حالیہ آرڈر مسترد یا واپس ہو سکتے ہیں، کیوں، اور بھیجنے سے پہلے کیا کرنا چاہیے۔",
  "High risk orders": "زیادہ رسک والے آرڈرز",
  "Medium risk orders": "درمیانے رسک والے آرڈرز",
  "Orders checked": "جانچے گئے آرڈرز",
  "Last 30 days of data": "ڈیٹا کے آخری 30 دن",
  "Recent orders": "حالیہ آرڈرز",
  "The orders that need action come first. The percentage is the model's estimate, not a fact.": "جن آرڈرز پر کارروائی چاہیے وہ پہلے ہیں۔ فیصد ماڈل کا اندازہ ہے، حقیقت نہیں۔",
  "Savings estimate": "بچت کا اندازہ",
  "What flagging these orders could have saved, worked out on past orders the model had not seen.": "ان آرڈرز کو نشان زد کرنے سے کتنی بچت ہو سکتی تھی، ان پرانے آرڈرز پر جو ماڈل نے نہیں دیکھے تھے۔",
  "Courier results": "کورئیر کے نتائج",
  "Real delivered and returned results make the model more accurate than cancelled orders alone.": "ڈیلیور اور واپس ہونے کے اصل نتائج ماڈل کو صرف منسوخ آرڈرز سے زیادہ درست بناتے ہیں۔",
  "No single factor stands out.": "کوئی ایک وجہ نمایاں نہیں۔",
  "More reasons": "مزید وجوہات",
  "The model's estimate, not a fact": "ماڈل کا اندازہ، حقیقت نہیں",
  "High risk": "زیادہ رسک",
  "Medium risk": "درمیانا رسک",
  "Low risk": "کم رسک",
  "All": "سب",
  "Filter by risk level": "رسک کی سطح سے چھانٹیں",
  "Showing the first {count} orders. The riskiest come first.": "پہلے {count} آرڈرز دکھائے جا رہے ہیں۔ سب سے زیادہ رسک والے پہلے ہیں۔",
  "No orders at this risk level in this period.": "اس مدت میں اس رسک کی سطح کا کوئی آرڈر نہیں۔",
  "Recent orders with their risk of being returned": "حالیہ آرڈرز اور ان کے واپس ہونے کا رسک",
  "Order": "آرڈر",
  "Amount": "رقم",
  "Risk": "رسک",
  "Why?": "کیوں؟",
  "What to do": "کیا کرنا ہے",
  "Show {count} more": "{count} مزید دکھائیں",
  "Shipping cost per parcel, both ways ({currency})": "فی پارسل شپنگ لاگت، دونوں طرف ({currency})",
  "Which orders to flag": "کن آرڈرز کو نشان زد کریں",
  "High risk only": "صرف زیادہ رسک",
  "High and Medium risk": "زیادہ اور درمیانا رسک",
  "Orders flagged": "نشان زد آرڈرز",
  "{returned} really came back ({share})": "{returned} واقعی واپس آئے ({share})",
  "False alarms": "غلط الارم",
  "Flagged, but delivered fine": "نشان زد ہوئے، مگر ٹھیک ڈیلیور ہوئے",
  "Estimated cost avoided": "بچنے والی اندازاً لاگت",
  "All returns in this period cost": "اس مدت میں تمام واپسیوں کی لاگت",
  "Enter the shipping cost to see it": "دیکھنے کے لیے شپنگ لاگت درج کریں",
  "The flagged orders include {share} of all returned orders in this period.": "نشان زد آرڈرز میں اس مدت کے تمام واپس شدہ آرڈرز کا {share} شامل ہے۔",
  "This is an estimate on past orders, not a promise.": "یہ پرانے آرڈرز پر ایک اندازہ ہے، وعدہ نہیں۔",
  "It uses {orders} orders from {start} to {end} that the model had not seen, and assumes every flagged order that came back would have been stopped.": "اس میں {start} سے {end} تک کے {orders} آرڈرز استعمال ہوئے جو ماڈل نے نہیں دیکھے تھے، اور فرض کیا گیا ہے کہ ہر نشان زد واپس آنے والا آرڈر روک لیا جاتا۔",
  "Labels": "لیبل",
  "The model learned from real courier results (delivered or returned).": "ماڈل نے کورئیر کے اصل نتائج (ڈیلیور یا واپس) سے سیکھا۔",
  "The model learned from orders that were later cancelled in your files, used as a stand-in for refused or returned parcels. Add courier results below to learn from real delivery outcomes.": "ماڈل نے ان آرڈرز سے سیکھا جو آپ کی فائلوں میں بعد میں منسوخ ہوئے، جنہیں مسترد یا واپس ہونے والے پارسلز کی جگہ استعمال کیا گیا۔ اصل ڈیلیوری نتائج سے سیکھنے کے لیے نیچے کورئیر کے نتائج شامل کریں۔",
  "The model learned from a mix of courier results and cancelled orders.": "ماڈل نے کورئیر کے نتائج اور منسوخ آرڈرز دونوں سے سیکھا۔",
  "Order risk model: estimates, not facts. Tested on unseen orders.": "آرڈر رسک ماڈل: اندازے، حقائق نہیں۔ نادیدہ آرڈرز پر جانچا گیا۔",
  "model": "ماڈل",
  "baseline": "بیس لائن",
  "baseline = the customer's own past return rate": "بیس لائن = کسٹمر کی اپنی پچھلی واپسی کی شرح",
  "Among the riskiest {share} of orders, {model} really came back (baseline: {baseline}).": "سب سے زیادہ رسک والے {share} آرڈرز میں سے {model} واقعی واپس آئے (بیس لائن: {baseline})۔",
  "Trained on {train} orders up to {end}, tested on {test} newer orders from {start}.": "{end} تک کے {train} آرڈرز پر تربیت دی گئی، اور {start} سے نئے {test} آرڈرز پر جانچا گیا۔",
  "Orders newer than {days} days are not used, because they may still be cancelled.": "{days} دن سے نئے آرڈرز استعمال نہیں ہوتے، کیونکہ وہ ابھی منسوخ ہو سکتے ہیں۔",
  "Levels: Low under {low}, High over {high}, Medium in between.": "سطحیں: کم {low} سے نیچے، زیادہ {high} سے اوپر، اور درمیانا ان کے بیچ۔",
  "Scores on orders it had not seen: model {model}, baseline {baseline} ({metric}).": "نادیدہ آرڈرز پر اسکور: ماڈل {model}، بیس لائن {baseline} ({metric})۔",
  "CustomerIQ AI shows an order's risk only when the model beats a simple baseline on orders it has not seen. Otherwise it shows nothing rather than an invented number.": "CustomerIQ AI آرڈر کا رسک تب ہی دکھاتا ہے جب ماڈل نادیدہ آرڈرز پر ایک سادہ بیس لائن کو ہرائے۔ ورنہ گھڑا ہوا نمبر دکھانے کے بجائے کچھ نہیں دکھاتا۔",
  "The file is larger than 10 MB.": "فائل 10 ایم بی سے بڑی ہے۔",
  "Something went wrong. Please try again.": "کچھ غلط ہو گیا۔ براہِ کرم دوبارہ کوشش کریں۔",
  "Upload a CSV or Excel file from your courier with these columns:": "اپنے کورئیر کی CSV یا ایکسل فائل اپ لوڈ کریں، جس میں یہ کالم ہوں:",
  "Status is delivered or returned. The orders must already be imported.": "اسٹیٹس delivered یا returned ہو۔ آرڈرز پہلے سے درآمد شدہ ہونے چاہییں۔",
  "Upload courier results": "کورئیر کے نتائج اپ لوڈ کریں",
  "Download the template": "ٹیمپلیٹ ڈاؤن لوڈ کریں",
  "The two example rows only show the format. Replace them with your own.": "دو مثال والی قطاریں صرف انداز دکھاتی ہیں۔ انہیں اپنی قطاروں سے بدل دیں۔",
  "{updated} orders updated ({returned} returned). {rejected} rows were rejected.": "{updated} آرڈرز اپ ڈیٹ ہوئے ({returned} واپس)۔ {rejected} قطاریں مسترد ہوئیں۔",
  "Row": "قطار",
  "risky orders need checking": "رسک والے آرڈرز کی جانچ ضروری ہے",
  "High": "زیادہ",
  "Medium": "درمیانا",
  "days": "دن",
  "See why": "وجہ دیکھیں",
  // Quick Order Entry ("Add Order"). Words in {braces} are replaced by numbers or names.
  "Add Order": "آرڈر شامل کریں",
  "Add an order you received in a chat in about ten seconds. It joins your customers and reports like any imported order.": "چیٹ میں ملا ہوا آرڈر تقریباً دس سیکنڈ میں شامل کریں۔ یہ دوسرے درآمد شدہ آرڈرز کی طرح آپ کے کسٹمرز اور رپورٹس میں شامل ہو جاتا ہے۔",
  "Phone number": "فون نمبر",
  "Customer name": "کسٹمر کا نام",
  "City": "شہر",
  "Products": "مصنوعات",
  "Add": "شامل کریں",
  "Type a product and press Enter": "مصنوعات کا نام لکھیں اور اینٹر دبائیں",
  "Remove {product}": "{product} ہٹائیں",
  "Use last products": "پچھلی مصنوعات استعمال کریں",
  "Amount (PKR)": "رقم (روپے)",
  "Payment": "ادائیگی",
  "Cash on delivery (COD)": "کیش آن ڈیلیوری (COD)",
  "Prepaid": "پیشگی ادائیگی",
  "Where did the order come from?": "آرڈر کہاں سے آیا؟",
  "Other": "دیگر",
  "Date": "تاریخ",
  "Note (optional)": "نوٹ (اختیاری)",
  "Save order": "آرڈر محفوظ کریں",
  "Saving…": "محفوظ ہو رہا ہے…",
  "New customer": "نیا کسٹمر",
  "New customer added.": "نیا کسٹمر شامل ہو گیا۔",
  "Returning customer: 1 past order": "پرانا کسٹمر: 1 پچھلا آرڈر",
  "Returning customer: {count} past orders": "پرانا کسٹمر: {count} پچھلے آرڈرز",
  "Returning customer: {count} orders in total.": "پرانا کسٹمر: کل {count} آرڈرز۔",
  "Last order: {date}": "آخری آرڈر: {date}",
  "Name and city were filled in from their last order.": "نام اور شہر ان کے آخری آرڈر سے بھر دیے گئے ہیں۔",
  "Enter a Pakistani mobile number, like 0300 1234567.": "پاکستانی موبائل نمبر لکھیں، جیسے 0300 1234567۔",
  "Order {id} saved for {name}.": "آرڈر {id} کسٹمر {name} کے لیے محفوظ ہو گیا۔",
  "Amounts are saved as typed, in Pakistani rupees. Your dashboards currently read your data as {currency}.": "رقم جیسی لکھی جائے ویسی ہی پاکستانی روپوں میں محفوظ ہوتی ہے۔ آپ کے ڈیش بورڈ ابھی آپ کے ڈیٹا کو {currency} سمجھ رہے ہیں۔",
  "Show my data in PKR": "میرا ڈیٹا روپوں میں دکھائیں",
  "Some fields need attention.": "کچھ خانوں پر توجہ درکار ہے۔",
  "Enter the customer's phone number.": "کسٹمر کا فون نمبر لکھیں۔",
  "Not a Pakistani mobile number. Use a format like 0300 1234567 or +92 300 1234567.": "یہ پاکستانی موبائل نمبر نہیں ہے۔ 0300 1234567 یا +92 300 1234567 جیسا انداز استعمال کریں۔",
  "Enter the customer's name.": "کسٹمر کا نام لکھیں۔",
  "The name is too long (100 characters at most).": "نام بہت لمبا ہے (زیادہ سے زیادہ 100 حروف)۔",
  "Enter the city.": "شہر لکھیں۔",
  "The city name is too long.": "شہر کا نام بہت لمبا ہے۔",
  "Add at least one product.": "کم از کم ایک مصنوعہ شامل کریں۔",
  "Add at most 20 products.": "زیادہ سے زیادہ 20 مصنوعات شامل کریں۔",
  "A product name is too long (100 characters at most).": "مصنوعہ کا نام بہت لمبا ہے (زیادہ سے زیادہ 100 حروف)۔",
  "Enter the amount.": "رقم لکھیں۔",
  "Enter the amount as a number, like 2500.": "رقم عدد میں لکھیں، جیسے 2500۔",
  "The amount must be more than 0.": "رقم 0 سے زیادہ ہونی چاہیے۔",
  "The amount is too large.": "رقم بہت زیادہ ہے۔",
  "Choose COD or prepaid.": "COD یا پیشگی ادائیگی چنیں۔",
  "Choose where the order came from.": "چنیں کہ آرڈر کہاں سے آیا۔",
  "Enter the date as YYYY-MM-DD.": "تاریخ YYYY-MM-DD انداز میں لکھیں۔",
  "The date is in the future.": "تاریخ مستقبل کی ہے۔",
  "The date is too far in the past.": "تاریخ بہت پرانی ہے۔",
  "The note is too long (500 characters at most).": "نوٹ بہت لمبا ہے (زیادہ سے زیادہ 500 حروف)۔",
  "This looks like the order you just added (same customer, amount and products). If it is a different order, change something and save again.": "یہ وہی آرڈر لگتا ہے جو آپ نے ابھی شامل کیا (وہی کسٹمر، رقم اور مصنوعات)۔ اگر یہ الگ آرڈر ہے تو کچھ بدل کر دوبارہ محفوظ کریں۔",
  "Adding orders needs the backend": "آرڈر شامل کرنے کے لیے بیک اینڈ چاہیے",
  // WhatsApp chat import. Words in {braces} are replaced by numbers or names.
  "Import WhatsApp Chat": "واٹس ایپ چیٹ درآمد کریں",
  "Import a WhatsApp chat": "واٹس ایپ چیٹ درآمد کریں",
  "Turn orders agreed in a WhatsApp chat into orders in CustomerIQ AI. You review every suggestion; nothing is saved until you accept it.": "واٹس ایپ چیٹ میں طے ہوئے آرڈرز کو CustomerIQ AI کے آرڈرز بنائیں۔ ہر تجویز آپ خود دیکھتے ہیں؛ جب تک آپ قبول نہ کریں کچھ محفوظ نہیں ہوتا۔",
  "Importing a chat needs the backend": "چیٹ درآمد کرنے کے لیے بیک اینڈ چاہیے",
  "In WhatsApp open the chat, choose Export chat, then Without media, and save the .txt file.": "واٹس ایپ میں چیٹ کھولیں، Export chat چنیں، پھر Without media، اور .txt فائل محفوظ کریں۔",
  "Before you upload a chat": "چیٹ اپ لوڈ کرنے سے پہلے",
  "Only upload chats with your own customers.": "صرف اپنے کسٹمرز کے ساتھ چیٹس اپ لوڈ کریں۔",
  "What is read: the messages in the file, to look for amounts, phone numbers, cities and order words.": "کیا پڑھا جاتا ہے: فائل کے پیغامات، تاکہ رقم، فون نمبر، شہر اور آرڈر کے الفاظ ڈھونڈے جائیں۔",
  "What is saved: only the orders you accept (name, phone, city, products, amount, payment type, date). The chat itself is never saved.": "کیا محفوظ ہوتا ہے: صرف وہ آرڈرز جو آپ قبول کریں (نام، فون، شہر، مصنوعات، رقم، ادائیگی کی قسم، تاریخ)۔ چیٹ خود کبھی محفوظ نہیں ہوتی۔",
  "The file is read in memory on the server and discarded straight away. You can delete everything imported from WhatsApp at any time below.": "فائل سرور کی میموری میں پڑھی جاتی ہے اور فوراً ضائع کر دی جاتی ہے۔ آپ نیچے سے کسی بھی وقت واٹس ایپ سے درآمد کیا گیا سب کچھ مٹا سکتے ہیں۔",
  "I will only upload chats with my own customers.": "میں صرف اپنے کسٹمرز کے ساتھ چیٹس اپ لوڈ کروں گا/گی۔",
  "Tick the box above to choose a file.": "فائل چننے کے لیے اوپر والا خانہ منتخب کریں۔",
  "Choose chat file (.txt)": "چیٹ فائل چنیں (.txt)",
  "Reading the chat…": "چیٹ پڑھی جا رہی ہے…",
  "This chat is too big (4 MB at most). Export fewer months of the chat and try again.": "یہ چیٹ بہت بڑی ہے (زیادہ سے زیادہ 4 ایم بی)۔ چیٹ کے کم مہینے ایکسپورٹ کر کے دوبارہ کوشش کریں۔",
  "Review the suggested orders": "تجویز کردہ آرڈرز کا جائزہ لیں",
  "Read {messages} messages. Skipped {system} app notices and {media} photos or other media.": "{messages} پیغامات پڑھے گئے۔ {system} ایپ کے نوٹس اور {media} تصاویر یا دیگر میڈیا چھوڑ دیے گئے۔",
  "Nothing is saved until you accept it.": "جب تک آپ قبول نہ کریں کچھ محفوظ نہیں ہوتا۔",
  "Which name is you (the seller)?": "ان میں سے آپ (بیچنے والے) کون سا نام ہیں؟",
  "Not sure": "یقین نہیں",
  "Your own messages are then not counted as order requests. Changing this restarts the review.": "پھر آپ کے اپنے پیغامات کو آرڈر کی درخواست نہیں گنا جاتا۔ اسے بدلنے سے جائزہ دوبارہ شروع ہوتا ہے۔",
  "How are the dates written?": "تاریخیں کس انداز میں لکھی ہیں؟",
  "Day first (02/03 = 2 March)": "پہلے دن (02/03 = 2 مارچ)",
  "Month first (02/03 = 3 February)": "پہلے مہینہ (02/03 = 3 فروری)",
  "Every date in this chat fits both ways, so please choose.": "اس چیٹ کی ہر تاریخ دونوں طرح درست بیٹھتی ہے، براہِ کرم چنیں۔",
  "No orders were found in this chat. Orders are recognised by amounts like Rs 2500, phone numbers and words like order, confirm or COD.": "اس چیٹ میں کوئی آرڈر نہیں ملا۔ آرڈر کی پہچان Rs 2500 جیسی رقم، فون نمبر اور order، confirm یا COD جیسے الفاظ سے ہوتی ہے۔",
  "{pending} to review · {accepted} accepted · {rejected} rejected": "{pending} جائزے کے لیے · {accepted} قبول · {rejected} مسترد",
  "Save {count} accepted orders": "{count} قبول شدہ آرڈرز محفوظ کریں",
  "More possible orders were found than are shown. Save these and import again.": "دکھائے گئے سے زیادہ ممکنہ آرڈرز ملے ہیں۔ انہیں محفوظ کریں اور دوبارہ درآمد کریں۔",
  "Some orders need attention.": "کچھ آرڈرز پر توجہ درکار ہے۔",
  "Saved {saved} orders ({customers} new customers).": "{saved} آرڈرز محفوظ ہو گئے ({customers} نئے کسٹمرز)۔",
  "{count} were already imported before.": "{count} پہلے ہی درآمد ہو چکے تھے۔",
  "Import another chat": "ایک اور چیٹ درآمد کریں",
  "Amount and phone found": "رقم اور فون ملا",
  "Only amount found": "صرف رقم ملی",
  "Only phone found": "صرف فون ملا",
  "Only keyword found": "صرف آرڈر کا لفظ ملا",
  "Original messages": "اصل پیغامات",
  "shown here only, never saved": "صرف یہاں دکھائے جاتے ہیں، کبھی محفوظ نہیں ہوتے",
  "Other amounts in this chat: {amounts}": "اس چیٹ میں دوسری رقمیں: {amounts}",
  "Products (type them from the messages)": "مصنوعات (پیغامات دیکھ کر لکھیں)",
  "Accept": "قبول کریں",
  "Reject": "مسترد کریں",
  "Accepted": "قبول شدہ",
  "Rejected": "مسترد شدہ",
  "Edit": "ترمیم",
  "Undo": "واپس",
  "No name": "نام نہیں",
  "This order will not be saved.": "یہ آرڈر محفوظ نہیں ہوگا۔",
  "Your imported WhatsApp data": "آپ کا درآمد شدہ واٹس ایپ ڈیٹا",
  "Orders you accepted from a chat. The chats themselves are never stored.": "چیٹ سے قبول کیے گئے آرڈرز۔ چیٹس خود کبھی محفوظ نہیں ہوتیں۔",
  "{orders} orders from {customers} customers were imported from WhatsApp chats.": "واٹس ایپ چیٹس سے {customers} کسٹمرز کے {orders} آرڈرز درآمد ہوئے۔",
  "Delete all imported WhatsApp data": "درآمد شدہ واٹس ایپ کا سارا ڈیٹا مٹائیں",
  "This deletes these orders, and customers who have no other orders. Orders from files or from Add Order are not touched. It cannot be undone.": "یہ ان آرڈرز کو مٹاتا ہے، اور ان کسٹمرز کو جن کا کوئی اور آرڈر نہیں۔ فائلوں یا Add Order سے آئے آرڈرز کو نہیں چھیڑا جاتا۔ اسے واپس نہیں کیا جا سکتا۔",
  "Yes, delete": "ہاں، مٹائیں",
  "Cancel": "منسوخ کریں",
  "Deleted {orders} orders and {customers} customers.": "{orders} آرڈرز اور {customers} کسٹمرز مٹا دیے گئے۔",
  "Unzip the export and upload the .txt file inside it.": "ایکسپورٹ کو ان زپ کریں اور اندر والی .txt فائل اپ لوڈ کریں۔",
  "WhatsApp chat export (.txt)": "واٹس ایپ چیٹ ایکسپورٹ (.txt)",
  // Seller sheet / templates.
  "Keep your orders in a sheet?": "کیا آپ آرڈرز شیٹ میں رکھتے ہیں؟",
  "Download the template, fill in one order per row, and upload it here. Upload it again as it grows: orders already imported are not added twice.": "ٹیمپلیٹ ڈاؤن لوڈ کریں، ہر قطار میں ایک آرڈر لکھیں اور یہاں اپ لوڈ کریں۔ شیٹ بڑھنے پر دوبارہ اپ لوڈ کریں: پہلے سے درآمد شدہ آرڈرز دوبارہ نہیں جڑتے۔",
  "Excel template": "ایکسل ٹیمپلیٹ",
  "In Google Sheets: File, Import, Upload the CSV template. When you are done, File, Download, CSV.": "گوگل شیٹس میں: File، Import، پھر CSV ٹیمپلیٹ اپ لوڈ کریں۔ کام ختم ہونے پر File، Download، CSV۔",
  // Dashboard: channel filter, revenue by channel, "how many more needed".
  "All channels": "تمام چینلز",
  "Filter by sales channel": "فروخت کے چینل سے چھانٹیں",
  "Showing figures for {channel} orders only. The revenue by channel chart below still compares all channels.": "صرف {channel} کے آرڈرز کے اعداد و شمار دکھائے جا رہے ہیں۔ نیچے چینل وار آمدنی کا چارٹ پھر بھی تمام چینلز کا موازنہ کرتا ہے۔",
  "Revenue by channel": "چینل وار آمدنی",
  "Where the orders came from, {start} to {end}. All channels are shown, whatever the filter is.": "آرڈرز کہاں سے آئے، {start} سے {end} تک۔ فلٹر کوئی بھی ہو، تمام چینلز دکھائے جاتے ہیں۔",
  "Where the orders came from.": "آرڈرز کہاں سے آئے۔",
  "Revenue, orders and customers for each sales channel": "ہر فروخت چینل کی آمدنی، آرڈرز اور کسٹمرز",
  "Channel": "چینل",
  "Share of revenue": "آمدنی کا حصہ",
  "Orders": "آرڈرز",
  "Customers": "کسٹمرز",
  "Not enough customers to segment": "گروپس بنانے کے لیے کسٹمرز کافی نہیں",
  "Not enough data yet: {count} more customers needed. Segmentation needs at least {minimum} customers.": "ابھی ڈیٹا کافی نہیں: {count} مزید کسٹمرز چاہییں۔ گروپس بنانے کے لیے کم از کم {minimum} کسٹمرز درکار ہیں۔",
  "No {channel} orders yet": "ابھی {channel} کا کوئی آرڈر نہیں",
  "There are no orders from this channel in your data. Add orders with Add Order, or choose another channel above.": "آپ کے ڈیٹا میں اس چینل کا کوئی آرڈر نہیں۔ Add Order سے آرڈرز شامل کریں، یا اوپر سے دوسرا چینل چنیں۔",
  // Add Order: platform for "Other".
  "Which platform? (optional)": "کون سا پلیٹ فارم؟ (اختیاری)",
  "For example TikTok, Daraz or walk-in": "مثال: TikTok، Daraz یا walk-in",
  "The platform name is too long (50 characters at most).": "پلیٹ فارم کا نام بہت لمبا ہے (زیادہ سے زیادہ 50 حروف)۔",
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

/** Translates a template such as "Returned {returned} of {total} earlier orders", then fills in the values. */
export function translateWith(language: Language, template: string, params: Record<string, string | number>) {
  return translate(language, template).replace(/\{(\w+)\}/g, (match, key: string) =>
    key in params ? String(params[key]) : match,
  );
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
  return {
    language,
    t: (text: string) => translate(language, text),
    tf: (template: string, params: Record<string, string | number>) => translateWith(language, template, params),
  };
}
