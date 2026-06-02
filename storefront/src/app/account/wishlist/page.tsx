"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ProductCard } from "@/components/product/ProductCard";
import { useWishlist } from "@/store/wishlist-store";
import { useAuth } from "@/store/auth-store";

export default function WishlistPage() {
  const customer = useAuth((s) => s.customer);
  const items = useWishlist((s) => s.items);
  const loading = useWishlist((s) => s.loading);
  const refresh = useWishlist((s) => s.refresh);
  const moveToCart = useWishlist((s) => s.moveToCart);
  const moveAllToCart = useWishlist((s) => s.moveAllToCart);
  const [movingId, setMovingId] = useState<number | null>(null);
  const [movingAll, setMovingAll] = useState(false);

  useEffect(() => {
    if (customer) refresh();
  }, [customer, refresh]);

  async function handleMove(productId: number) {
    setMovingId(productId);
    try {
      await moveToCart(productId);
    } finally {
      setMovingId(null);
    }
  }

  const inStockCount = items.filter((p) => p.in_stock).length;

  async function handleMoveAll() {
    setMovingAll(true);
    try {
      await moveAllToCart();
    } finally {
      setMovingAll(false);
    }
  }

  if (!customer) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <h1 className="mb-4 font-editorial text-4xl">Wishlist</h1>
        <p className="mb-8 text-sm text-ink/60">
          Masuk untuk menyimpan dan melihat produk favorit Anda.
        </p>
        <Link
          href="/account/login"
          className="inline-block bg-ink px-10 py-4 text-xs uppercase tracking-[0.2em] text-bone hover:opacity-90"
        >
          Sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-10">
      <div className="mb-10 flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="font-editorial text-4xl">Wishlist</h1>
        {items.length > 0 && (
          <div className="flex items-center gap-5">
            <span className="text-xs uppercase tracking-[0.16em] text-ink/50">
              {items.length} item{items.length > 1 ? "s" : ""}
            </span>
            <button
              onClick={handleMoveAll}
              disabled={inStockCount === 0 || movingAll}
              className="bg-ink px-6 py-3 text-[11px] uppercase tracking-[0.2em] text-bone transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {movingAll ? "Moving…" : "Move all to cart"}
            </button>
          </div>
        )}
      </div>

      {loading && items.length === 0 ? (
        <p className="py-20 text-center text-sm text-ink/40">Loading…</p>
      ) : items.length === 0 ? (
        <div className="py-20 text-center">
          <p className="mb-6 text-sm text-ink/50">Wishlist Anda masih kosong.</p>
          <Link
            href="/products"
            className="inline-block border border-ink px-10 py-4 text-xs uppercase tracking-[0.2em] transition-colors hover:bg-ink hover:text-bone"
          >
            Jelajahi koleksi
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-x-6 gap-y-12 md:grid-cols-4">
          {items.map((p, i) => (
            <div key={p.id} className="flex flex-col">
              <ProductCard product={p} index={i} />
              <button
                onClick={() => handleMove(p.id)}
                disabled={!p.in_stock || movingId === p.id}
                className="mt-3 w-full bg-ink py-3 text-[11px] uppercase tracking-[0.2em] text-bone transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {!p.in_stock
                  ? "Sold out"
                  : movingId === p.id
                    ? "Moving…"
                    : "Move to cart"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
