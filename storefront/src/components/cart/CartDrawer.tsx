"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { X, Minus, Plus, Trash2 } from "lucide-react";
import { useEffect } from "react";
import { useCart } from "@/store/cart-store";
import { useAuth } from "@/store/auth-store";
import { imageUrl } from "@/lib/client";
import { formatPrice } from "@/lib/format";

export function CartDrawer() {
  const { cart, drawerOpen, setDrawer, refresh, setQty, remove } = useCart();
  const customer = useAuth((s) => s.customer);
  const authReady = useAuth((s) => s.ready);

  useEffect(() => {
    if (authReady && drawerOpen && customer) refresh();
  }, [authReady, drawerOpen, customer, refresh]);

  const lines = (cart?.lines ?? []).filter((l) => !l.is_delivery);

  return (
    <AnimatePresence>
      {drawerOpen && (
        <>
          <motion.div
            className="fixed inset-0 z-50 bg-ink/40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setDrawer(false)}
          />
          <motion.aside
            className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col bg-bone shadow-2xl"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 260 }}
          >
            <div className="flex items-center justify-between border-b border-ink/10 px-6 py-5">
              <h2 className="font-editorial text-lg uppercase tracking-[0.2em]">Cart</h2>
              <button onClick={() => setDrawer(false)} aria-label="Close">
                <X className="h-5 w-5" strokeWidth={1.4} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-4">
              {!customer ? (
                <p className="mt-10 text-center text-sm text-ink/60">
                  Please{" "}
                  <Link href="/account/login" className="underline" onClick={() => setDrawer(false)}>
                    sign in
                  </Link>{" "}
                  to view your cart.
                </p>
              ) : lines.length === 0 ? (
                <p className="mt-10 text-center text-sm text-ink/60">Your cart is empty.</p>
              ) : (
                lines.map((line) => (
                  <div key={line.id} className="flex gap-4 border-b border-ink/5 py-4">
                    <div className="h-20 w-16 shrink-0 overflow-hidden bg-sand">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={imageUrl(line.image)} alt={line.name} className="h-full w-full object-cover" />
                    </div>
                    <div className="flex flex-1 flex-col justify-between">
                      <div className="flex justify-between">
                        <p className="text-sm">{line.name}</p>
                        <button onClick={() => remove(line.id)} aria-label="Remove">
                          <Trash2 className="h-4 w-4 text-ink/40" strokeWidth={1.4} />
                        </button>
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3 border border-ink/15 px-2 py-1">
                          <button onClick={() => setQty(line.id, line.qty - 1)} aria-label="Decrease">
                            <Minus className="h-3 w-3" />
                          </button>
                          <span className="text-sm">{line.qty}</span>
                          <button onClick={() => setQty(line.id, line.qty + 1)} aria-label="Increase">
                            <Plus className="h-3 w-3" />
                          </button>
                        </div>
                        <span className="text-sm">{formatPrice(line.price_subtotal, cart?.currency)}</span>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {customer && lines.length > 0 && (
              <div className="border-t border-ink/10 px-6 py-5">
                <div className="mb-4 flex justify-between text-sm">
                  <span className="text-ink/60">Subtotal</span>
                  <span>{formatPrice(cart?.amount_total ?? 0, cart?.currency)}</span>
                </div>
                <Link
                  href="/checkout"
                  onClick={() => setDrawer(false)}
                  className="block bg-ink py-4 text-center text-xs uppercase tracking-[0.2em] text-bone transition-opacity hover:opacity-90"
                >
                  Checkout
                </Link>
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
