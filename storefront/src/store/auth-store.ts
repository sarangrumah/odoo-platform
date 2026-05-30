"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Customer } from "@/lib/types";

interface AuthState {
  customer: Customer | null;
  isGuest: boolean;
  setSession: (s: { customer: Customer; is_guest?: boolean }) => void;
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
      setSession: (s) => set({ customer: s.customer, isGuest: !!s.is_guest }),
      clear: () => set({ customer: null, isGuest: false }),
    }),
    { name: "gw-auth" },
  ),
);
