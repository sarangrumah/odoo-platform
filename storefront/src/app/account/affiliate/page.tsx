"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Copy, Check } from "lucide-react";
import { fetchAffiliateMe, applyAffiliate, createAffiliateLink } from "@/lib/client";
import { useAuth } from "@/store/auth-store";
import { formatPrice } from "@/lib/format";
import type { AffiliateDashboard, AffiliateLink } from "@/lib/types";

function ShareRow({ url, label }: { url: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const text = encodeURIComponent(`${label} — Gentle Woman`);
  const u = encodeURIComponent(url);
  const targets = [
    { key: "WhatsApp", href: `https://wa.me/?text=${text}%20${u}` },
    { key: "Facebook", href: `https://www.facebook.com/sharer/sharer.php?u=${u}` },
    { key: "X", href: `https://twitter.com/intent/tweet?url=${u}&text=${text}` },
    { key: "Telegram", href: `https://t.me/share/url?url=${u}&text=${text}` },
  ];
  async function copy() {
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.14em]">
      {targets.map((t) => (
        <a
          key={t.key}
          href={t.href}
          target="_blank"
          rel="noopener noreferrer"
          className="border border-ink/20 px-3 py-1.5 transition-colors hover:border-ink"
        >
          {t.key}
        </a>
      ))}
      <button
        onClick={copy}
        className="flex items-center gap-1 border border-ink/20 px-3 py-1.5 transition-colors hover:border-ink"
      >
        {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

export default function AffiliatePage() {
  const customer = useAuth((s) => s.customer);
  const [data, setData] = useState<AffiliateDashboard | null>(null);
  const [busy, setBusy] = useState(false);
  const [linkName, setLinkName] = useState("");
  const [linkTarget, setLinkTarget] = useState("/");

  useEffect(() => {
    if (customer) fetchAffiliateMe().then(setData).catch(() => setData(null));
  }, [customer]);

  if (!customer) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <h1 className="mb-4 font-editorial text-4xl">Affiliate</h1>
        <p className="mb-8 text-sm text-ink/60">Masuk untuk mengakses program afiliasi.</p>
        <Link href="/account/login" className="inline-block bg-ink px-10 py-4 text-xs uppercase tracking-[0.2em] text-bone hover:opacity-90">
          Sign in
        </Link>
      </div>
    );
  }

  async function apply() {
    if (!customer) return;
    setBusy(true);
    try {
      setData(await applyAffiliate());
    } finally {
      setBusy(false);
    }
  }

  async function addLink(e: React.FormEvent) {
    e.preventDefault();
    if (!customer) return;
    setBusy(true);
    try {
      setData(await createAffiliateLink(linkName || "Link", linkTarget || "/"));
      setLinkName("");
      setLinkTarget("/");
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return <div className="mx-auto max-w-5xl px-6 py-20 text-center text-ink/40">Loading…</div>;
  }

  if (!data.is_affiliate) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <h1 className="mb-4 font-editorial text-4xl">Jadi Affiliate</h1>
        <p className="mb-8 text-sm text-ink/60">
          Bagikan produk Gentle Woman dan dapatkan komisi dari setiap pembelian melalui tautan Anda.
        </p>
        <button onClick={apply} disabled={busy}
          className="inline-block bg-ink px-10 py-4 text-xs uppercase tracking-[0.2em] text-bone hover:opacity-90 disabled:opacity-50">
          {busy ? "Memproses…" : "Daftar sekarang"}
        </button>
      </div>
    );
  }

  const s = data.stats!;
  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="font-editorial text-4xl">Affiliate</h1>
        <span className="text-xs uppercase tracking-[0.16em] text-ink/50">
          Kode: <span className="text-ink">{data.code}</span> · Komisi {data.commission_rate}% · {data.state}
        </span>
      </div>

      {/* Stats */}
      <div className="mt-8 grid grid-cols-2 gap-px bg-ink/10 md:grid-cols-4">
        {[
          { label: "Klik", value: String(s.clicks) },
          { label: "Konversi", value: String(s.conversions.approved + s.conversions.paid + s.conversions.pending) },
          { label: "Komisi disetujui", value: formatPrice(s.earned, data.currency) },
          { label: "Komisi pending", value: formatPrice(s.pending, data.currency) },
        ].map((c) => (
          <div key={c.label} className="bg-bone p-5">
            <p className="text-[11px] uppercase tracking-[0.16em] text-ink/50">{c.label}</p>
            <p className="mt-1 font-editorial text-2xl">{c.value}</p>
          </div>
        ))}
      </div>

      {/* Link generator */}
      <h2 className="eyebrow mt-12 mb-3">Buat tautan terlacak</h2>
      <form onSubmit={addLink} className="flex flex-wrap gap-3">
        <input value={linkName} onChange={(e) => setLinkName(e.target.value)} placeholder="Label (mis. Tote IG)"
          className="flex-1 min-w-[12rem] border border-ink/20 bg-transparent px-4 py-3 text-sm" />
        <input value={linkTarget} onChange={(e) => setLinkTarget(e.target.value)} placeholder="/products/6 atau /"
          className="flex-1 min-w-[12rem] border border-ink/20 bg-transparent px-4 py-3 text-sm" />
        <button disabled={busy} className="bg-ink px-6 py-3 text-xs uppercase tracking-[0.2em] text-bone hover:opacity-90 disabled:opacity-50">
          {busy ? "…" : "Generate"}
        </button>
      </form>

      {/* Links */}
      <div className="mt-8 space-y-5">
        {(data.links ?? []).length === 0 && (
          <p className="text-sm text-ink/50">Belum ada tautan. Buat tautan pertama Anda di atas.</p>
        )}
        {(data.links ?? []).map((l: AffiliateLink) => (
          <div key={l.id} className="border border-ink/10 p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-sm">{l.name}</span>
              <span className="text-[11px] uppercase tracking-[0.16em] text-ink/40">{l.click_count} klik</span>
            </div>
            <p className="mt-1 break-all text-xs text-ink/50">{l.full_url}</p>
            <ShareRow url={l.full_url} label={l.name} />
          </div>
        ))}
      </div>
    </div>
  );
}
