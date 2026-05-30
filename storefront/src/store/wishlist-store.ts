"use client";

import { create } from "zustand";
import type { Product } from "@/lib/types";
import * as api from "@/lib/client";
import { useAuth } from "./auth-store";
import { useCart } from "./cart-store";

interface WishlistState {
  items: Product[];
  ids: number[];
  loading: boolean;
  refresh: () => Promise<void>;
  toggle: (productId: number) => Promise<void>;
  moveToCart: (productId: number) => Promise<void>;
  moveAllToCart: () => Promise<number>;
  clearLocal: () => void;
}

function authed(): boolean {
  return !!useAuth.getState().customer;
}

/**
 * Wishlist mirror. Odoo (`custom.wishlist`, partner-scoped) is authoritative —
 * every mutation returns the recomputed list, stored verbatim. Auth is the
 * BFF's HttpOnly cookie; `ids` lights up the heart toggles.
 */
export const useWishlist = create<WishlistState>()((set, get) => ({
  items: [],
  ids: [],
  loading: false,

  refresh: async () => {
    if (!authed()) return set({ items: [], ids: [] });
    set({ loading: true });
    try {
      const items = await api.fetchWishlist();
      set({ items, ids: items.map((i) => i.id) });
    } finally {
      set({ loading: false });
    }
  },

  toggle: async (productId) => {
    if (!authed()) throw new Error("AUTH_REQUIRED");
    const wished = get().ids.includes(productId);
    set({ loading: true });
    try {
      const items = wished
        ? await api.removeWishlist(productId)
        : await api.addWishlist(productId);
      set({ items, ids: items.map((i) => i.id) });
    } finally {
      set({ loading: false });
    }
  },

  moveToCart: async (productId) => {
    if (!authed()) throw new Error("AUTH_REQUIRED");
    set({ loading: true });
    try {
      const { cart, wishlist } = await api.moveWishlistToCart(productId);
      set({ items: wishlist, ids: wishlist.map((i) => i.id) });
      useCart.getState().setCart(cart, true);
    } finally {
      set({ loading: false });
    }
  },

  moveAllToCart: async () => {
    if (!authed()) throw new Error("AUTH_REQUIRED");
    set({ loading: true });
    try {
      const { cart, wishlist, moved } = await api.moveAllWishlistToCart();
      set({ items: wishlist, ids: wishlist.map((i) => i.id) });
      if (moved > 0) useCart.getState().setCart(cart, true);
      return moved;
    } finally {
      set({ loading: false });
    }
  },

  clearLocal: () => set({ items: [], ids: [] }),
}));
