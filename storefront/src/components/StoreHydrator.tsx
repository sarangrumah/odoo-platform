"use client";

import { useEffect } from "react";
import { useAuth } from "@/store/auth-store";
import { useLocale } from "@/store/locale-store";

/**
 * The persisted stores use `skipHydration` so the server HTML and the first
 * client render are identical (defaults) — no React hydration mismatch. Once
 * the tree is mounted and hydration is complete, we pull the saved values from
 * localStorage; the resulting re-render is a normal client update, not part of
 * hydration, so it is safe.
 */
export function StoreHydrator() {
  useEffect(() => {
    useAuth.persist.rehydrate();
    useLocale.persist.rehydrate();
  }, []);
  return null;
}
