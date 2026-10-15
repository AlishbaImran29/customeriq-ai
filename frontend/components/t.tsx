"use client";

import { useLanguage } from "@/lib/i18n";

/** Shows its English text in the chosen language (falls back to English). */
export function T({ children }: { children: string }) {
  const { t } = useLanguage();
  return <>{t(children)}</>;
}
