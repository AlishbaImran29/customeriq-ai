"use client";

import { Languages } from "lucide-react";
import { LANGUAGES, setLanguage, useLanguage, type Language } from "@/lib/i18n";

export function LanguageToggle() {
  const { language } = useLanguage();
  return (
    <label className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 focus-within:ring-2 focus-within:ring-teal-500/40">
      <Languages className="h-3.5 w-3.5 text-teal-700" aria-hidden="true" />
      <span className="sr-only">Language</span>
      <select
        value={language}
        onChange={(event) => setLanguage(event.target.value as Language)}
        className="cursor-pointer bg-transparent text-xs font-medium focus:outline-none"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.name}
          </option>
        ))}
      </select>
    </label>
  );
}
