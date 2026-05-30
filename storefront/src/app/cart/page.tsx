"use client";

import Link from "next/link";
import { useEffect } from "react";
import { Minus, Plus, Trash2 } from "lucide-react";
import { useCart } from "@/store/cart-store";
import { useAuth } from "@/store/auth-store";
import { imageUrl } from "@/lib/client";
import { formatPrice } from "@/lib/format";

export default function CartPage() {
  const { cart, refresh, setQty, remove } = useCart();
  const customer = useAuth((s) => s.customer);

  useEffect(() => {
    if (customer) refresh();
  }, [customer, refresh]);

  if (!customer) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-24 text-center">
        <p className="text-ink/60">
          Please{" "}
          <Link href="/account/login" className="underline">sign in</Link> to view your cart.
        </p>
      </div>
    );
  }

  const lines = (cart?.lines ?? []).filter((l) => !l.is_delivery);

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <h1 className="mb-10 font-editorial text-4xl">Your Cart</h1>
      {lines.length === 0 ? (
        <p className="py-16 text-center text-ink/50">
          Your cart is empty. <Link href="/products" className="underline">Continue shopping</Link>.
        </p>
      ) : (
        <div className="grid gap-12 md:grid-cols-3">
          <div className="md:col-span-2">
            {lines.map((line) => (
              <div key={line.id} className="flex gap-5 border-b border-ink/10 py-6">
                <div className="h-28 w-24 shrink-0 overflow-hidden bg-sand">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={imageUrl(line.image)} alt={line.name} className="h-full w-full object-cover" />
                </div>
                <div className="flex flex-1 flex-col justify-between">
                  <div className="flex justify-between">
                    <p>{line.name}</p>
                    <button onClick={() => remove(line.id)} aria-label="Remove">
                      <Trash2 className="h-4 w-4 text-ink/40" strokeWidth={1.4} />
                    </button>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 border border-ink/15 px-3 py-1.5">
                      <button onClick={() => setQty(line.id, line.qty - 1)}><Minus className="h-3 w-3" /></button>
                      <span className="text-sm">{line.qty}</span>
                      <button onClick={() => setQty(line.id, line.qty + 1)}><Plus className="h-3 w-3" /></button>
                    </div>
                    <span>{formatPrice(line.price_subtotal, cart?.currency)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="h-fit border border-ink/10 bg-sand/30 p-6">
            <h2 className="eyebrow mb-6">Summary</h2>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-ink/60">Subtotal</span><span>{formatPrice(cart?.amount_untaxed ?? 0, cart?.currency)}</span></div>
              <div className="flex justify-between"><span className="text-ink/60">Tax</span><span>{formatPrice(cart?.amount_tax ?? 0, cart?.currency)}</span></div>
              <div className="flex justify-between border-t border-ink/10 pt-3 text-base"><span>Total</span><span>{formatPrice(cart?.amount_total ?? 0, cart?.currency)}</span></div>
            </div>
            <Link
              href="/checkout"
              className="mt-6 block bg-ink py-4 text-center text-xs uppercase tracking-[0.2em] text-bone hover:opacity-90"
            >
              Checkout
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
