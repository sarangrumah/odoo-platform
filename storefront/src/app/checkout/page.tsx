"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useCart } from "@/store/cart-store";
import { useAuth } from "@/store/auth-store";
import {
  applyShipping,
  checkout as doCheckout,
  createAddress,
  fetchMe,
  fetchShippingQuotes,
  fetchStores,
  setCartPickup,
  payOrder,
} from "@/lib/client";
import { formatPrice } from "@/lib/format";
import { getAffiliateCode } from "@/lib/affiliate";
import type { CustomerAddress, ShippingAddress, ShippingQuote, Store } from "@/lib/types";

const EMPTY_ADDR: ShippingAddress = { name: "", phone: "", street: "", city: "", zip: "" };

export default function CheckoutPage() {
  const router = useRouter();
  const { cart, refresh } = useCart();
  const { customer, isGuest } = useAuth();
  const [quotes, setQuotes] = useState<ShippingQuote[]>([]);
  const [carrierId, setCarrierId] = useState<number | null>(null);
  const [mode, setMode] = useState<"delivery" | "pickup">("delivery");
  const [stores, setStores] = useState<Store[]>([]);
  const [pickupStoreId, setPickupStoreId] = useState<number | null>(null);
  const [addr, setAddr] = useState<ShippingAddress>(EMPTY_ADDR);
  const [saved, setSaved] = useState<CustomerAddress[]>([]);
  const [savedInvoice, setSavedInvoice] = useState<CustomerAddress[]>([]);
  const [selectedAddrId, setSelectedAddrId] = useState<number | null>(null);
  const [addingNew, setAddingNew] = useState(false);
  const [billingSame, setBillingSame] = useState(true);
  const [billingAddrId, setBillingAddrId] = useState<number | null>(null);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!customer) router.push("/account/login");
    else refresh();
  }, [customer, refresh, router]);

  // Load saved addresses (members); default-select the first.
  useEffect(() => {
    if (!customer) return;
    fetchMe()
      .then(({ addresses }) => {
        const delivery = addresses.filter((a) => a.type === "delivery");
        setSaved(delivery);
        setSavedInvoice(addresses.filter((a) => a.type === "invoice"));
        if (delivery.length) setSelectedAddrId(delivery[0].id);
        else setAddingNew(true);
      })
      .catch(() => setAddingNew(true));
  }, [customer]);

  // Prefill the new-address name from the signed-in / guest customer once.
  useEffect(() => {
    if (customer?.name) setAddr((a) => (a.name ? a : { ...a, name: customer.name }));
  }, [customer]);

  function setAddrField(k: keyof ShippingAddress) {
    return (e: React.ChangeEvent<HTMLInputElement>) => setAddr((a) => ({ ...a, [k]: e.target.value }));
  }
  const addrComplete = !!(addr.street?.trim() && addr.city?.trim());

  async function saveNewAddress() {
    if (!customer || !addrComplete) return;
    setBusy(true);
    try {
      const { id } = await createAddress(addr);
      const { addresses } = await fetchMe();
      setSaved(addresses.filter((a) => a.type === "delivery"));
      setSelectedAddrId(id);
      setAddingNew(false);
      setAddr(EMPTY_ADDR);
    } catch (e) {
      setStatus(String(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    fetchStores().then(setStores).catch(() => setStores([]));
  }, []);

  useEffect(() => {
    const lines = (cart?.lines ?? []).filter((l) => !l.is_delivery);
    if (!lines.length) return;
    fetchShippingQuotes(lines.map((l) => ({ product_id: l.product_id, qty: l.qty })))
      .then(setQuotes)
      .catch(() => setQuotes([]));
  }, [cart]);

  async function chooseCarrier(id: number) {
    if (!customer) return;
    setCarrierId(id);
    try {
      await applyShipping(id);
      await refresh();
    } catch (e) {
      setStatus(String(e));
    }
  }

  async function choosePickupStore(id: number) {
    if (!customer) return;
    setPickupStoreId(id);
    setCarrierId(null);
    try {
      await setCartPickup(id);
      await refresh();
    } catch (e) {
      setStatus(String(e));
    }
  }

  async function placeOrder() {
    if (!customer) return;
    setBusy(true);
    setStatus("Creating order…");
    try {
      const affiliate_code = getAffiliateCode() || undefined;
      const order = await doCheckout({
        ...(mode === "pickup" && pickupStoreId
          ? { pickup_warehouse_id: pickupStoreId }
          : {
              ...(carrierId ? { carrier_id: carrierId } : {}),
              ...(selectedAddrId && !addingNew
                ? { shipping_address_id: selectedAddrId }
                : { shipping_address: addr }),
              ...(!billingSame && billingAddrId ? { billing_address_id: billingAddrId } : {}),
            }),
        ...(affiliate_code ? { affiliate_code } : {}),
      });
      setStatus("Initiating Eraspace payment…");
      const pay = await payOrder(order.order_id, "eraspace");
      setStatus(`Order ${order.name} created. Redirecting to payment…`);
      await refresh();
      // Stubbed Eraspace returns a placeholder hosted-checkout URL.
      if (pay.redirect_url) {
        window.location.href = pay.redirect_url;
      } else {
        router.push(`/account/orders/${order.order_id}`);
      }
    } catch (e) {
      setStatus(`Failed: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  const lines = (cart?.lines ?? []).filter((l) => !l.is_delivery);

  return (
    <div className="mx-auto grid max-w-5xl gap-12 px-6 py-12 md:grid-cols-2">
      <div>
        <h1 className="mb-8 font-editorial text-4xl">Checkout</h1>
        <div className="mb-5 flex gap-2">
          {(["delivery", "pickup"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`flex-1 border px-4 py-3 text-[11px] uppercase tracking-[0.18em] transition-colors ${
                mode === m ? "border-ink bg-ink text-bone" : "border-ink/20 text-ink/60 hover:border-ink"
              }`}
            >
              {m === "delivery" ? "Dikirim" : "Ambil di toko"}
            </button>
          ))}
        </div>

        {mode === "delivery" ? (
          <>
            <p className="eyebrow mb-3">Alamat pengiriman</p>

            {/* Saved addresses (members) */}
            {saved.length > 0 && (
              <div className="mb-4 space-y-2">
                {saved.map((a) => (
                  <label
                    key={a.id}
                    className={`flex cursor-pointer items-start gap-3 border px-4 py-3 text-sm ${
                      selectedAddrId === a.id && !addingNew ? "border-ink" : "border-ink/15"
                    }`}
                  >
                    <input
                      type="radio"
                      name="saved-addr"
                      className="mt-1"
                      checked={selectedAddrId === a.id && !addingNew}
                      onChange={() => {
                        setSelectedAddrId(a.id);
                        setAddingNew(false);
                      }}
                    />
                    <span>
                      <span className="block">{a.name}</span>
                      <span className="block text-xs text-ink/50">
                        {[a.street, a.city, a.zip].filter(Boolean).join(", ")}
                        {a.phone ? ` · ${a.phone}` : ""}
                      </span>
                    </span>
                  </label>
                ))}
                <button
                  type="button"
                  onClick={() => setAddingNew((v) => !v)}
                  className="text-[11px] uppercase tracking-[0.16em] text-accent underline"
                >
                  {addingNew ? "Pakai alamat tersimpan" : "+ Tambah alamat baru"}
                </button>
              </div>
            )}

            {/* New address form (guests, or members adding a new one) */}
            {addingNew && (
              <div className="mb-6 space-y-3">
                <div className="flex flex-col gap-3 sm:flex-row">
                  <input placeholder="Nama penerima" value={addr.name} onChange={setAddrField("name")}
                    className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
                  <input placeholder="No. telepon" value={addr.phone} onChange={setAddrField("phone")}
                    className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
                </div>
                <input placeholder="Alamat lengkap (jalan, no.)" value={addr.street} onChange={setAddrField("street")}
                  className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
                <div className="flex flex-col gap-3 sm:flex-row">
                  <input placeholder="Kota" value={addr.city} onChange={setAddrField("city")}
                    className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
                  <input placeholder="Kode pos" value={addr.zip} onChange={setAddrField("zip")}
                    className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
                </div>
                {!isGuest && (
                  <button
                    type="button"
                    onClick={saveNewAddress}
                    disabled={!addrComplete || busy}
                    className="border border-ink px-6 py-2.5 text-[11px] uppercase tracking-[0.18em] transition-colors hover:bg-ink hover:text-bone disabled:opacity-40"
                  >
                    Simpan alamat
                  </button>
                )}
              </div>
            )}

            {/* Billing address */}
            <label className="mb-3 flex items-center gap-2 text-sm text-ink/70">
              <input type="checkbox" checked={billingSame} onChange={(e) => setBillingSame(e.target.checked)} className="h-4 w-4 accent-ink" />
              Alamat penagihan sama dengan pengiriman
            </label>
            {!billingSame && (
              <div className="mb-6">
                {savedInvoice.length > 0 ? (
                  <select
                    value={billingAddrId ?? ""}
                    onChange={(e) => setBillingAddrId(e.target.value ? Number(e.target.value) : null)}
                    className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm"
                  >
                    <option value="">Pilih alamat penagihan…</option>
                    {savedInvoice.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} — {[a.street, a.city].filter(Boolean).join(", ")}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="text-xs text-ink/50">
                    Belum ada alamat penagihan.{" "}
                    <a href="/account/addresses" className="underline hover:text-accent">Tambah di Alamat saya</a>.
                  </p>
                )}
              </div>
            )}

            <p className="eyebrow mb-3">Kurir</p>
            <div className="space-y-2">
              {quotes.length === 0 && <p className="text-sm text-ink/50">No carriers available.</p>}
              {quotes.map((q) => (
                <label
                  key={q.carrier_id}
                  className={`flex cursor-pointer items-center justify-between border px-4 py-3 text-sm ${
                    carrierId === q.carrier_id ? "border-ink" : "border-ink/15"
                  }`}
                >
                  <span className="flex items-center gap-3">
                    <input
                      type="radio"
                      name="carrier"
                      checked={carrierId === q.carrier_id}
                      onChange={() => chooseCarrier(q.carrier_id)}
                    />
                    {q.name} {q.etd_days ? `· ${q.etd_days} days` : ""} {q.cod_supported ? "· COD" : ""}
                  </span>
                  <span>{formatPrice(q.price, q.currency)}</span>
                </label>
              ))}
            </div>
          </>
        ) : (
          <>
            <p className="eyebrow mb-3">Pilih toko (gratis ongkir)</p>
            <div className="space-y-2">
              {stores.length === 0 && <p className="text-sm text-ink/50">Belum ada toko.</p>}
              {stores.map((s) => (
                <label
                  key={s.id}
                  className={`flex cursor-pointer items-start gap-3 border px-4 py-3 text-sm ${
                    pickupStoreId === s.id ? "border-ink" : "border-ink/15"
                  }`}
                >
                  <input
                    type="radio"
                    name="pickup-store"
                    className="mt-1"
                    checked={pickupStoreId === s.id}
                    onChange={() => choosePickupStore(s.id)}
                  />
                  <span>
                    <span className="block">{s.name.replace(/^Gentle Woman — /, "")}</span>
                    <span className="block text-xs text-ink/50">{s.address}</span>
                  </span>
                </label>
              ))}
            </div>
          </>
        )}

        <p className="mt-8 eyebrow mb-3">Payment</p>
        <div className="border border-ink/15 px-4 py-3 text-sm text-ink/70">
          Eraspace (sandbox) — you will be redirected to complete payment.
        </div>

        <button
          onClick={placeOrder}
          disabled={
            busy ||
            lines.length === 0 ||
            (mode === "pickup" ? !pickupStoreId : !addrComplete)
          }
          className="mt-10 w-full bg-ink py-5 text-xs uppercase tracking-[0.25em] text-bone hover:opacity-90 disabled:opacity-40"
        >
          {busy ? "Processing…" : "Place order"}
        </button>
        {status && <p className="mt-4 text-sm text-accent">{status}</p>}
      </div>

      <div className="h-fit border border-ink/10 bg-sand/30 p-6">
        <h2 className="eyebrow mb-6">Order Summary</h2>
        {lines.map((l) => (
          <div key={l.id} className="flex justify-between py-1 text-sm">
            <span className="text-ink/70">{l.name} × {l.qty}</span>
            <span>{formatPrice(l.price_subtotal, cart?.currency)}</span>
          </div>
        ))}
        <div className="mt-4 flex justify-between border-t border-ink/10 pt-4 text-base">
          <span>Total</span>
          <span>{formatPrice(cart?.amount_total ?? 0, cart?.currency)}</span>
        </div>
      </div>
    </div>
  );
}
