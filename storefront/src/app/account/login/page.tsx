"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { login, guestLogin } from "@/lib/client";
import { useAuth } from "@/store/auth-store";
import { useCart } from "@/store/cart-store";
import { useWishlist } from "@/store/wishlist-store";

export default function LoginPage() {
  const router = useRouter();
  const setSession = useAuth((s) => s.setSession);
  const refreshCart = useCart((s) => s.refresh);
  const refreshWishlist = useWishlist((s) => s.refresh);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Guest checkout
  const [guestEmail, setGuestEmail] = useState("");
  const [guestName, setGuestName] = useState("");
  const [guestConsent, setGuestConsent] = useState(false);
  const [guestBusy, setGuestBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const session = await login(email, password);
      setSession(session);
      await Promise.all([refreshCart(), refreshWishlist()]);
      router.push("/account/orders");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function continueAsGuest(e: React.FormEvent) {
    e.preventDefault();
    if (!guestConsent) {
      setError("Anda harus menyetujui pemrosesan data untuk melanjutkan.");
      return;
    }
    setGuestBusy(true);
    setError("");
    try {
      const session = await guestLogin(guestEmail, guestName, guestConsent);
      setSession(session);
      await refreshCart();
      router.push("/checkout");
    } catch (err) {
      setError(String(err));
    } finally {
      setGuestBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md px-6 py-20">
      <h1 className="mb-8 font-editorial text-4xl">Sign In</h1>
      <form onSubmit={submit} className="space-y-4">
        <input
          type="email" required placeholder="Email" value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm"
        />
        <input
          type="password" required placeholder="Password" value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm"
        />
        {error && <p className="text-sm text-red-700">{error}</p>}
        <button
          disabled={busy}
          className="w-full bg-ink py-4 text-xs uppercase tracking-[0.2em] text-bone hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-ink/60">
        New here? <Link href="/account/register" className="underline">Create an account</Link>
      </p>

      {/* Guest checkout — no account needed */}
      <div className="my-10 flex items-center gap-4 text-[11px] uppercase tracking-[0.2em] text-ink/40">
        <span className="h-px flex-1 bg-ink/15" /> atau / or <span className="h-px flex-1 bg-ink/15" />
      </div>
      <h2 className="mb-4 font-editorial text-2xl">Checkout sebagai tamu</h2>
      <form onSubmit={continueAsGuest} className="space-y-4">
        <input
          required placeholder="Nama / Name" value={guestName}
          onChange={(e) => setGuestName(e.target.value)}
          className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm"
        />
        <input
          type="email" required placeholder="Email" value={guestEmail}
          onChange={(e) => setGuestEmail(e.target.value)}
          className="w-full border border-ink/20 bg-transparent px-4 py-3 text-sm"
        />
        <label className="flex items-start gap-3 text-xs leading-relaxed text-ink/70">
          <input type="checkbox" checked={guestConsent} onChange={(e) => setGuestConsent(e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-ink" />
          <span>Saya menyetujui pemrosesan data untuk memproses pesanan (UU PDP). <span className="text-accent">*</span></span>
        </label>
        <button
          disabled={guestBusy}
          className="w-full border border-ink py-4 text-xs uppercase tracking-[0.2em] transition-colors hover:bg-ink hover:text-bone disabled:opacity-50"
        >
          {guestBusy ? "…" : "Lanjut sebagai tamu"}
        </button>
      </form>
    </div>
  );
}
