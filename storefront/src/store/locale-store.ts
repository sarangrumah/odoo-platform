"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import { translate, type Locale, DEFAULT_LOCALE } from "@/lib/i18n";

interface LocaleState {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string) => string;
}

/**
 * Storefront UI language. Persisted to localStorage; `lib/client.ts` reads it
 * via `useLocale.getState().locale` to send `?lang=` so Odoo returns translated
 * catalog content. `t()` resolves UI chrome strings from the dictionary.
 */
export const useLocale = create<LocaleState>()(
  persist(
    (set, get) => ({
      locale: DEFAULT_LOCALE,
      setLocale: (l) => set({ locale: l }),
      t: (key) => translate(get().locale, key),
    }),
    { name: "gw-locale" },
  ),
);
