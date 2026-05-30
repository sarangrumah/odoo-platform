"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useLocale } from "@/store/locale-store";
import { LOCALES, type Locale } from "@/lib/i18n";

function localeFromUrl(): Locale | null {
  if (typeof window === "undefined") return null;
  const seg = window.location.pathname.split("/")[1];
  return (LOCALES as string[]).includes(seg) ? (seg as Locale) : null;
}

/** Keeps the locale store (UI strings + ?lang=) in sync with the URL prefix. */
export function LocaleSync() {
  const setLocale = useLocale((s) => s.setLocale);
  const pathname = usePathname();

  useEffect(() => {
    const loc = localeFromUrl();
    if (loc) {
      setLocale(loc);
      document.documentElement.lang = loc;
    }
  }, [pathname, setLocale]);

  return null;
}
