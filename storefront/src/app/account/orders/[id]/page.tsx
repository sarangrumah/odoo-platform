"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/store/auth-store";
import { fetchOrder } from "@/lib/client";
import { formatPrice } from "@/lib/format";
import type { Cart } from "@/lib/types";

interface OrderDetail extends Cart {
  payment: { state: string; reference: string } | null;
}

export default function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { customer } = useAuth();
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!customer) {
      router.push("/account/login");
      return;
    }
    fetchOrder(id)
      .then((o) => setOrder(o as OrderDetail))
      .catch((e) => setError(String(e)));
  }, [customer, id, router]);

  if (error) return <div className="mx-auto max-w-3xl px-6 py-20 text-red-700">{error}</div>;
  if (!order) return <div className="mx-auto max-w-3xl px-6 py-20 text-ink/40">Loading…</div>;

  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="font-editorial text-4xl">{order.name}</h1>
      <div className="mt-3 flex gap-4 text-xs uppercase tracking-widest text-ink/50">
        <span>Order: {order.state}</span>
        {order.payment && <span>Payment: {order.payment.state}</span>}
        {order.awb_number && <span>AWB: {order.awb_number}</span>}
      </div>

      <div className="mt-10 divide-y divide-ink/10 border-y border-ink/10">
        {order.lines.map((l) => (
          <div key={l.id} className="flex justify-between py-4 text-sm">
            <span className="text-ink/70">{l.name} {l.is_delivery ? "(shipping)" : `× ${l.qty}`}</span>
            <span>{formatPrice(l.price_subtotal, order.currency)}</span>
          </div>
        ))}
      </div>

      <div className="mt-6 flex justify-between text-lg">
        <span>Total</span>
        <span>{formatPrice(order.amount_total, order.currency)}</span>
      </div>

      {order.awb_tracking_url && (
        <a href={order.awb_tracking_url} target="_blank" rel="noreferrer"
          className="mt-8 inline-block border border-ink px-8 py-3 text-xs uppercase tracking-[0.2em] hover:bg-ink hover:text-bone">
          Track shipment
        </a>
      )}
    </div>
  );
}
