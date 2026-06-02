"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchOrders, logout } from "@/lib/client";
import { useAuth } from "@/store/auth-store";
import { formatPrice } from "@/lib/format";

type Order = Awaited<ReturnType<typeof fetchOrders>>[number];

export default function OrdersPage() {
  const router = useRouter();
  const { customer, clear } = useAuth();
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!customer) {
      router.push("/account/login");
      return;
    }
    fetchOrders().then(setOrders).catch((e) => setError(String(e)));
  }, [customer, router]);

  async function signOut() {
    await logout();
    clear();
    router.push("/");
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <div className="mb-10 flex items-center justify-between">
        <h1 className="font-editorial text-4xl">My Orders</h1>
        <button onClick={signOut} className="text-xs uppercase tracking-[0.2em] text-accent">
          Sign out
        </button>
      </div>
      {customer && (
        <p className="mb-8 text-sm text-ink/60">
          Signed in as {customer.email} ·{" "}
          <Link href="/account/addresses" className="underline hover:text-accent">Alamat</Link> ·{" "}
          <Link href="/account/wishlist" className="underline hover:text-accent">Wishlist</Link> ·{" "}
          <Link href="/account/affiliate" className="underline hover:text-accent">Affiliate</Link>
        </p>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
      {orders.length === 0 ? (
        <p className="py-16 text-center text-ink/50">
          No orders yet. <Link href="/products" className="underline">Start shopping</Link>.
        </p>
      ) : (
        <div className="divide-y divide-ink/10 border-y border-ink/10">
          {orders.map((o) => (
            <Link key={o.order_id} href={`/account/orders/${o.order_id}`}
              className="flex items-center justify-between py-5 transition-colors hover:bg-sand/30">
              <div>
                <p className="text-sm">{o.name}</p>
                <p className="text-xs uppercase tracking-widest text-ink/40">{o.state}</p>
              </div>
              <span className="text-sm">{formatPrice(o.amount_total, o.currency)}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
