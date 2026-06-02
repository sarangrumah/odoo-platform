"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { register } from "@/lib/client";
import { useAuth } from "@/store/auth-store";

export default function RegisterPage() {
  const router = useRouter();
  const setSession = useAuth((s) => s.setSession);
  const [form, setForm] = useState({ name: "", email: "", password: "", phone: "" });
  const [consentData, setConsentData] = useState(false);
  const [consentMarketing, setConsentMarketing] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function update(key: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [key]: e.target.value }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!consentData) {
      setError("Anda harus menyetujui pemrosesan data untuk mendaftar.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const session = await register({
        ...form,
        consent_data: consentData,
        consent_marketing: consentMarketing,
      });
      setSession(session);
      router.push("/products");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md px-6 py-20">
      <h1 className="mb-8 font-editorial text-4xl">Create Account</h1>
      <form onSubmit={submit} className="space-y-4">
        <input required placeholder="Full name" value={form.name} onChange={update("name")}
          className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
        <input type="email" required placeholder="Email" value={form.email} onChange={update("email")}
          className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
        <input type="tel" placeholder="Phone (optional)" value={form.phone} onChange={update("phone")}
          className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />
        <input type="password" required placeholder="Password (min 8 chars)" value={form.password} onChange={update("password")}
          className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm" />

        <label className="flex items-start gap-3 text-xs leading-relaxed text-ink/70">
          <input type="checkbox" checked={consentData} onChange={(e) => setConsentData(e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-ink" />
          <span>
            Saya menyetujui pemrosesan data pribadi saya sesuai Kebijakan Privasi (UU PDP). <span className="text-accent">*</span>
          </span>
        </label>
        <label className="flex items-start gap-3 text-xs leading-relaxed text-ink/70">
          <input type="checkbox" checked={consentMarketing} onChange={(e) => setConsentMarketing(e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-ink" />
          <span>Saya ingin menerima penawaran &amp; berita produk (opsional).</span>
        </label>

        {error && <p className="text-sm text-red-700">{error}</p>}
        <button disabled={busy}
          className="w-full bg-ink py-4 text-xs uppercase tracking-[0.2em] text-bone hover:opacity-90 disabled:opacity-50">
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-ink/60">
        Already have an account? <Link href="/account/login" className="underline">Sign in</Link>
      </p>
    </div>
  );
}
