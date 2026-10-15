"use client";

import { Languages } from "lucide-react";
import { setLanguage, useLanguage } from "@/lib/i18n";

export function LanguageToggle() {
  const { language } = useLanguage();
  const next = language === "en" ? "ur" : "en";
  return (
    <button
      type="button"
      onClick={() => setLanguage(next)}
      className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/40"
      aria-label={language === "en" ? "Switch to Urdu" : "Switch to English"}
    >
      <Languages className="h-3.5 w-3.5 text-teal-700" aria-hidden="true" />
      {language === "en" ? "اردو" : "English"}
    </button>
  );
}
