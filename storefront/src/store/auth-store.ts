"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Customer } from "@/lib/types";

interface AuthState {
  customer: Customer | null;
  isGuest: boolean;
  /** False until the server-side session probe (StoreHydrator → /auth/session)
   *  has reconciled the persisted profile. Authed side-effects (wishlist/cart
   *  auto-refresh) gate on this so they never fire against a stale session. */
  ready: boolean;
  setSession: (s: { customer: Customer; is_guest?: boolean }) => void;
  setReady: () => void;
  clear: () => void;
}

/**
 * Holds ONLY the non-sensitive customer profile. Auth tokens live in HttpOnly
 * cookies set by the BFF (see `lib/session.ts`) and are never readable by JS,
 * so an XSS cannot steal a session. `customer` is the "logged in" signal.
 */
export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      customer: null,
      isGuest: false,
      ready: false,
      setSession: (s) => set({ customer: s.customer, isGuest: !!s.is_guest }),
      setReady: () => set({ ready: true }),
      clear: () => set({ customer: null, isGuest: false }),
    }),
    // skipHydration: the server and the first client render both start from
    // these defaults, so there is no SSR/client divergence. `StoreHydrator`
    // pulls the persisted profile from localStorage once mounted.
    // partialize: only the profile is persisted — `ready` is runtime-only and
    // must always start false so the session is re-verified on every load.
    {
      name: "gw-auth",
      skipHydration: true,
      partialize: (s) => ({ customer: s.customer, isGuest: s.isGuest }),
    },
  ),
);
