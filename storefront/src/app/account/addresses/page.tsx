"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Pencil, Trash2 } from "lucide-react";
import { fetchMe, createAddress, updateAddress, deleteAddress } from "@/lib/client";
import { useAuth } from "@/store/auth-store";
import type { CustomerAddress, ShippingAddress } from "@/lib/types";

type Form = ShippingAddress & { type: string };
const EMPTY: Form = { type: "delivery", name: "", phone: "", street: "", city: "", zip: "" };

const TYPE_LABEL: Record<string, string> = {
  delivery: "Pengiriman",
  invoice: "Penagihan",
  other: "Lainnya",
};

export default function AddressesPage() {
  const customer = useAuth((s) => s.customer);
  const [list, setList] = useState<CustomerAddress[]>([]);
  const [form, setForm] = useState<Form>(EMPTY);
  const [editId, setEditId] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function reload() {
    if (!customer) return;
    const { addresses } = await fetchMe();
    setList(addresses);
  }
  useEffect(() => {
    if (customer) reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customer]);

  if (!customer) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <h1 className="mb-4 font-editorial text-4xl">Alamat</h1>
        <Link href="/account/login" className="inline-block bg-ink px-10 py-4 text-xs uppercase tracking-[0.2em] text-bone hover:opacity-90">
          Sign in
        </Link>
      </div>
    );
  }

  function field(k: keyof Form) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm((f) => ({ ...f, [k]: e.target.value }));
  }
  function startNew() {
    setForm({ ...EMPTY, name: customer?.name || "" });
    setEditId(null);
    setOpen(true);
  }
  function startEdit(a: CustomerAddress) {
    setForm({ type: a.type, name: a.name, phone: a.phone || "", street: a.street || "", city: a.city || "", zip: a.zip || "" });
    setEditId(a.id);
    setOpen(true);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!customer || !form.street?.trim() || !form.city?.trim()) return;
    setBusy(true);
    try {
      if (editId) await updateAddress(editId, form);
      else await createAddress(form);
      setOpen(false);
      setForm(EMPTY);
      setEditId(null);
      await reload();
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    if (!customer) return;
    await deleteAddress(id);
    await reload();
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <div className="mb-10 flex items-center justify-between">
        <h1 className="font-editorial text-4xl">Alamat saya</h1>
        <Link href="/account/orders" className="text-xs uppercase tracking-[0.2em] text-accent">
          ← Akun
        </Link>
      </div>

      <div className="space-y-3">
        {list.length === 0 && <p className="text-sm text-ink/50">Belum ada alamat tersimpan.</p>}
        {list.map((a) => (
          <div key={a.id} className="flex items-start justify-between border border-ink/15 p-5">
            <div>
              <p className="text-sm">
                {a.name}
                <span className="ml-2 border border-ink/20 px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-ink/50">
                  {TYPE_LABEL[a.type] || a.type}
                </span>
              </p>
              <p className="mt-1 text-xs text-ink/55">
                {[a.street, a.city, a.zip].filter(Boolean).join(", ")}
                {a.phone ? ` · ${a.phone}` : ""}
              </p>
            </div>
            <div className="flex gap-3 text-ink/50">
              <button onClick={() => startEdit(a)} aria-label="Edit" className="hover:text-accent">
                <Pencil className="h-4 w-4" />
              </button>
              <button onClick={() => remove(a.id)} aria-label="Hapus" className="hover:text-accent">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {!open ? (
        <button
          onClick={startNew}
          className="mt-8 border border-ink px-8 py-3 text-xs uppercase tracking-[0.2em] transition-colors hover:bg-ink hover:text-bone"
        >
          + Tambah alamat
        </button>
      ) : (
        <form onSubmit={save} className="mt-8 space-y-3 border border-ink/15 p-6">
          <h2 className="eyebrow mb-2">{editId ? "Ubah alamat" : "Alamat baru"}</h2>
          <select value={form.type} onChange={field("type")} className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm">
            <option value="delivery">Pengiriman</option>
            <option value="invoice">Penagihan</option>
          </select>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input placeholder="Nama" value={form.name} onChange={field("name")} className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
            <input placeholder="No. telepon" value={form.phone} onChange={field("phone")} className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
          </div>
          <input placeholder="Alamat lengkap (jalan, no.)" value={form.street} onChange={field("street")} className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
          <div className="flex flex-col gap-3 sm:flex-row">
            <input placeholder="Kota" value={form.city} onChange={field("city")} className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
            <input placeholder="Kode pos" value={form.zip} onChange={field("zip")} className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
          </div>
          <div className="flex gap-3">
            <button disabled={busy} className="bg-ink px-7 py-3 text-xs uppercase tracking-[0.2em] text-bone hover:opacity-90 disabled:opacity-50">
              {busy ? "…" : "Simpan"}
            </button>
            <button type="button" onClick={() => { setOpen(false); setEditId(null); }} className="px-5 py-3 text-xs uppercase tracking-[0.2em] text-ink/50">
              Batal
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
