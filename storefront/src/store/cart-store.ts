"use client";

import { create } from "zustand";
import type { Cart } from "@/lib/types";
import * as api from "@/lib/client";
import { useAuth } from "./auth-store";

interface CartState {
  cart: Cart | null;
  loading: boolean;
  drawerOpen: boolean;
  setDrawer: (open: boolean) => void;
  setCart: (cart: Cart, openDrawer?: boolean) => void;
  refresh: () => Promise<void>;
  add: (productId: number, qty?: number) => Promise<void>;
  setQty: (lineId: number, qty: number) => Promise<void>;
  remove: (lineId: number) => Promise<void>;
}

function authed(): boolean {
  return !!useAuth.getState().customer;
}

/**
 * Cart mirror. Odoo (the website_sale draft sale.order) is authoritative —
 * every mutation returns the recomputed cart, stored verbatim. Auth is the
 * HttpOnly cookie injected by the BFF; the client just needs a logged-in
 * customer to act.
 */
export const useCart = create<CartState>()((set) => ({
  cart: null,
  loading: false,
  drawerOpen: false,
  setDrawer: (open) => set({ drawerOpen: open }),
  setCart: (cart, openDrawer = false) =>
    set(openDrawer ? { cart, drawerOpen: true } : { cart }),

  refresh: async () => {
    if (!authed()) return set({ cart: null });
    set({ loading: true });
    try {
      set({ cart: await api.getCart() });
    } catch (e) {
      // Same as the wishlist: a 401 here means the persisted customer outlived
      // its session cookie. Drop the stale cart + dead session instead of
      // leaking an unhandled rejection.
      set({ cart: null });
      if ((e as { status?: number })?.status === 401) useAuth.getState().clear();
    } finally {
      set({ loading: false });
    }
  },

  add: async (productId, qty = 1) => {
    if (!authed()) throw new Error("AUTH_REQUIRED");
    set({ loading: true });
    try {
      set({ cart: await api.addToCart(productId, qty), drawerOpen: true });
    } finally {
      set({ loading: false });
    }
  },

  setQty: async (lineId, qty) => {
    if (!authed()) return;
    set({ loading: true });
    try {
      set({ cart: await api.setCartLineQty(lineId, qty) });
    } finally {
      set({ loading: false });
    }
  },

  remove: async (lineId) => {
    if (!authed()) return;
    set({ loading: true });
    try {
      set({ cart: await api.removeCartLine(lineId) });
    } finally {
      set({ loading: false });
    }
  },
}));
