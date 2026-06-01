"use client";

import { useEffect } from "react";
import { useAuth } from "@/store/auth-store";
import { useLocale } from "@/store/locale-store";
import { fetchSession } from "@/lib/client";

/**
 * The persisted stores use `skipHydration` so the server HTML and the first
 * client render are identical (defaults) — no React hydration mismatch. Once
 * the tree is mounted and hydration is complete, we pull the saved values from
 * localStorage; the resulting re-render is a normal client update, not part of
 * hydration, so it is safe.
 *
 * We then reconcile the (possibly stale) persisted profile against the server's
 * HttpOnly session cookie via /auth/session. Only after that resolves do we
 * mark auth `ready`, which gates authed side-effects (wishlist/cart refresh) —
 * so they never fire against a dead session and produce a 401.
 */
export function StoreHydrator() {
  useEffect(() => {
    useAuth.persist.rehydrate();
    useLocale.persist.rehydrate();

    let cancelled = false;
    fetchSession()
      .then((s) => {
        if (cancelled) return;
        if (s.authenticated && s.customer) useAuth.getState().setSession({ customer: s.customer });
        else useAuth.getState().clear();
      })
      .catch(() => {
        if (!cancelled) useAuth.getState().clear();
      })
      .finally(() => {
        if (!cancelled) useAuth.getState().setReady();
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return null;
}
