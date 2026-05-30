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
  fetchPaymentMethods,
  fetchShippingQuotes,
  fetchStores,
  setCartPickup,
  payOrder,
  submitPaymentProof,
} from "@/lib/client";
import { formatPrice } from "@/lib/format";
import { getAffiliateCode } from "@/lib/affiliate";
import type { CustomerAddress, PaymentMethod, ShippingAddress, ShippingQuote, Store } from "@/lib/types";

const EMPTY_ADDR: ShippingAddress = { name: "", phone: "", street: "", city: "", zip: "" };

type ManualState = {
  orderId: number;
  orderName: string;
  reference: string;
  instructions: string;
  provider: string;
  amount: number;
};

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

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

  // Payment methods (manual transfer + published gateways).
  const [methods, setMethods] = useState<PaymentMethod[]>([]);
  const [selectedCode, setSelectedCode] = useState<string>("");

  // Manual bank transfer flow (shown after the order is placed).
  const [manual, setManual] = useState<ManualState | null>(null);
  const [proofAmount, setProofAmount] = useState<number>(0);
  const [proofRef, setProofRef] = useState("");
  const [proofSender, setProofSender] = useState("");
  const [proofDate, setProofDate] = useState("");
  const [proofNote, setProofNote] = useState("");
  const [proofImage, setProofImage] = useState<string>("");
  const [proofFilename, setProofFilename] = useState("");
  const [proofBusy, setProofBusy] = useState(false);
  const [proofDone, setProofDone] = useState(false);

  useEffect(() => {
    if (!customer) router.push("/account/login");
    else refresh();
  }, [customer, refresh, router]);

  // Load published payment methods; default-select the configured default.
  useEffect(() => {
    fetchPaymentMethods()
      .then(({ default: def, methods }) => {
        setMethods(methods);
        const fallback = methods[0]?.code ?? "";
        setSelectedCode(def && methods.some((m) => m.code === def) ? def : fallback);
      })
      .catch(() => setMethods([]));
  }, []);

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
    setStatus("Membuat pesanan…");
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
      setStatus("Memproses pembayaran…");
      const pay = await payOrder(order.order_id, selectedCode || undefined);
      await refresh();
      if (pay.type === "redirect") {
        if (pay.redirect_url) {
          setStatus(`Pesanan ${order.name} dibuat. Mengarahkan ke pembayaran…`);
          window.location.href = pay.redirect_url;
          return;
        }
        router.push(`/account/orders/${order.order_id}`);
        return;
      }
      // Manual bank transfer — show instructions + proof form.
      setManual({
        orderId: order.order_id,
        orderName: order.name,
        reference: pay.reference,
        instructions: pay.instructions,
        provider: pay.provider,
        amount: order.amount_total,
      });
      setProofAmount(order.amount_total);
      setStatus("");
    } catch (e) {
      setStatus(`Gagal: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  async function onProofFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const dataUrl = await fileToDataUrl(file);
      setProofImage(dataUrl);
      setProofFilename(file.name);
    } catch {
      setStatus("Gagal membaca file.");
    }
  }

  async function sendProof() {
    if (!manual) return;
    setProofBusy(true);
    try {
      await submitPaymentProof(manual.orderId, {
        amount: proofAmount,
        bank_reference: proofRef || undefined,
        sender_name: proofSender || undefined,
        paid_date: proofDate || undefined,
        note: proofNote || undefined,
        image: proofImage || undefined,
        filename: proofFilename || undefined,
      });
      setProofDone(true);
    } catch (e) {
      setStatus(`Gagal mengirim bukti: ${e}`);
    } finally {
      setProofBusy(false);
    }
  }

  const lines = (cart?.lines ?? []).filter((l) => !l.is_delivery);

  return (
    <div className="mx-auto grid max-w-5xl gap-12 px-6 py-12 md:grid-cols-2">
      <div>
        <h1 className="mb-8 font-editorial text-4xl">Checkout</h1>

        {manual ? (
          <div className="space-y-6">
            <div className="border border-ink/15 bg-sand/30 p-5">
              <p className="eyebrow mb-2">Pesanan dibuat</p>
              <p className="text-sm text-ink/70">
                Pesanan <b>{manual.orderName}</b> menunggu pembayaran via <b>{manual.provider}</b>.
              </p>
              <p className="mt-2 text-sm">
                Berita / referensi transfer: <b className="font-mono">{manual.reference}</b>
              </p>
            </div>

            {manual.instructions && (
              <div className="border border-ink/15 p-5">
                <p className="eyebrow mb-3">Instruksi transfer</p>
                <div
                  className="prose prose-sm max-w-none text-ink/80"
                  dangerouslySetInnerHTML={{ __html: manual.instructions }}
                />
              </div>
            )}

            {proofDone ? (
              <div className="border border-ink/15 bg-sand/30 p-5">
                <p className="eyebrow mb-2">Bukti diterima</p>
                <p className="text-sm text-ink/70">
                  Terima kasih. Bukti transfer Anda sudah kami terima dan akan diverifikasi tim kami.
                </p>
                <button
                  onClick={() => router.push(`/account/orders/${manual.orderId}`)}
                  className="mt-4 border border-ink px-6 py-2.5 text-[11px] uppercase tracking-[0.18em] transition-colors hover:bg-ink hover:text-bone"
                >
                  Lihat pesanan
                </button>
              </div>
            ) : (
              <div className="border border-ink/15 p-5">
                <p className="eyebrow mb-3">Konfirmasi pembayaran</p>
                <p className="mb-4 text-xs text-ink/50">
                  Setelah transfer, isi detail di bawah dan unggah bukti agar pesanan diproses.
                </p>
                <div className="space-y-3">
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <input
                      type="number"
                      placeholder="Nominal ditransfer"
                      value={proofAmount || ""}
                      onChange={(e) => setProofAmount(Number(e.target.value))}
                      className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm"
                    />
                    <input
                      type="date"
                      value={proofDate}
                      onChange={(e) => setProofDate(e.target.value)}
                      className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm"
                    />
                  </div>
                  <input
                    placeholder="Nama pengirim"
                    value={proofSender}
                    onChange={(e) => setProofSender(e.target.value)}
                    className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm"
                  />
                  <input
                    placeholder="No. referensi / bank pengirim"
                    value={proofRef}
                    onChange={(e) => setProofRef(e.target.value)}
                    className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm"
                  />
                  <textarea
                    placeholder="Catatan (opsional)"
                    value={proofNote}
                    onChange={(e) => setProofNote(e.target.value)}
                    className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm"
                    rows={2}
                  />
                  <label className="block text-xs text-ink/60">
                    Bukti transfer (gambar)
                    <input
                      type="file"
                      accept="image/*"
                      onChange={onProofFile}
                      className="mt-1 block w-full text-sm"
                    />
                  </label>
                  {proofFilename && <p className="text-xs text-ink/50">Terlampir: {proofFilename}</p>}
                </div>
                <button
                  onClick={sendProof}
                  disabled={proofBusy || !proofAmount}
                  className="mt-5 w-full bg-ink py-4 text-xs uppercase tracking-[0.25em] text-bone hover:opacity-90 disabled:opacity-40"
                >
                  {proofBusy ? "Mengirim…" : "Kirim bukti transfer"}
                </button>
                <button
                  onClick={() => router.push(`/account/orders/${manual.orderId}`)}
                  className="mt-3 w-full text-[11px] uppercase tracking-[0.16em] text-ink/50 underline"
                >
                  Nanti saja, ke halaman pesanan
                </button>
              </div>
            )}
            {status && <p className="mt-4 text-sm text-accent">{status}</p>}
          </div>
        ) : (
          <>
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

            <p className="mt-8 eyebrow mb-3">Pembayaran</p>
            <div className="space-y-2">
              {methods.length === 0 && (
                <p className="text-sm text-ink/50">Belum ada metode pembayaran aktif.</p>
              )}
              {methods.map((m) => (
                <label
                  key={m.code}
                  className={`flex cursor-pointer items-center gap-3 border px-4 py-3 text-sm ${
                    selectedCode === m.code ? "border-ink" : "border-ink/15"
                  }`}
                >
                  <input
                    type="radio"
                    name="paymethod"
                    checked={selectedCode === m.code}
                    onChange={() => setSelectedCode(m.code)}
                  />
                  <span className="flex-1">
                    <span className="block">
                      {m.label}
                      {m.sandbox ? " · sandbox" : ""}
                    </span>
                    <span className="block text-xs text-ink/50">
                      {m.type === "manual"
                        ? "Transfer bank manual — instruksi tampil setelah pesanan dibuat"
                        : "Anda akan diarahkan ke halaman pembayaran"}
                    </span>
                  </span>
                </label>
              ))}
            </div>

            <button
              onClick={placeOrder}
              disabled={
                busy ||
                lines.length === 0 ||
                !selectedCode ||
                (mode === "pickup" ? !pickupStoreId : !addrComplete)
              }
              className="mt-10 w-full bg-ink py-5 text-xs uppercase tracking-[0.25em] text-bone hover:opacity-90 disabled:opacity-40"
            >
              {busy ? "Processing…" : "Place order"}
            </button>
            {status && <p className="mt-4 text-sm text-accent">{status}</p>}
          </>
        )}
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
