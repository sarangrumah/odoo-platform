"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, useScroll, useTransform } from "framer-motion";
import { Heart, ShoppingBag, User } from "lucide-react";
import { useCart } from "@/store/cart-store";
import { useAuth } from "@/store/auth-store";
import { useWishlist } from "@/store/wishlist-store";
import { useLocale } from "@/store/locale-store";
import { useUI } from "@/store/ui-store";
import { LOCALES } from "@/lib/i18n";

const SITE = process.env.NEXT_PUBLIC_SITE_NAME || "Gentle Woman";

export function Header() {
  const { scrollY } = useScroll();
  const bg = useTransform(scrollY, [0, 80], ["rgba(245,241,234,0)", "rgba(245,241,234,0.92)"]);
  const border = useTransform(scrollY, [0, 80], ["rgba(26,23,20,0)", "rgba(26,23,20,0.12)"]);

  const lines = useCart((s) => s.cart?.lines ?? []);
  const count = lines.filter((l) => !l.is_delivery).reduce((n, l) => n + l.qty, 0);
  const setDrawer = useCart((s) => s.setDrawer);
  const customer = useAuth((s) => s.customer);
  const locale = useLocale((s) => s.locale);
  const setLocale = useLocale((s) => s.setLocale);
  const t = useLocale((s) => s.t);
  const announcement = useUI((s) => s.announcement);
  const router = useRouter();

  function switchLocale(l: (typeof LOCALES)[number]) {
    setLocale(l); // snappy UI; LocaleSync re-affirms from the URL
    if (typeof window === "undefined") return;
    const parts = window.location.pathname.split("/");
    if ((LOCALES as string[]).includes(parts[1])) parts[1] = l;
    else parts.splice(1, 0, l);
    router.push((parts.join("/") || `/${l}`) + window.location.search);
  }

  // Hydrate the wishlist site-wide once a session exists, so heart toggles
  // reflect saved items on every page (PLP/PDP) — not just the wishlist page.
  const refreshWishlist = useWishlist((s) => s.refresh);
  const clearWishlist = useWishlist((s) => s.clearLocal);
  const wishCount = useWishlist((s) => s.ids.length);
  useEffect(() => {
    if (customer) refreshWishlist();
    else clearWishlist();
  }, [customer, refreshWishlist, clearWishlist]);

  return (
    <motion.header
      style={{
        backgroundColor: bg,
        borderBottom: "1px solid",
        borderColor: border,
        top: announcement ? "2.25rem" : 0,
      }}
      className="fixed left-0 right-0 z-40 backdrop-blur-sm"
    >
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
        <div className="flex gap-8 text-xs uppercase tracking-[0.18em]">
          <Link href="/products" className="hover:text-accent transition-colors">{t("nav.shop")}</Link>
          <Link href="/products?sort=newest" className="hover:text-accent transition-colors">{t("nav.new")}</Link>
          <Link href="/stores" className="hover:text-accent transition-colors">{t("nav.stores")}</Link>
        </div>

        <Link href="/" className="font-editorial text-2xl tracking-[0.3em] uppercase">
          {SITE}
        </Link>

        <div className="flex items-center gap-6">
          <div className="flex items-center gap-1 text-[11px] uppercase tracking-[0.16em]">
            {LOCALES.map((l, i) => (
              <span key={l} className="flex items-center">
                {i > 0 && <span className="mx-1 text-ink/30">/</span>}
                <button
                  onClick={() => switchLocale(l)}
                  className={locale === l ? "text-ink" : "text-ink/40 hover:text-accent"}
                  aria-pressed={locale === l}
                >
                  {l.toUpperCase()}
                </button>
              </span>
            ))}
          </div>
          <Link href={customer ? "/account/orders" : "/account/login"} aria-label="Account">
            <User className="h-5 w-5" strokeWidth={1.4} />
          </Link>
          <Link href="/account/wishlist" className="relative" aria-label="Wishlist">
            <Heart className="h-5 w-5" strokeWidth={1.4} />
            {wishCount > 0 && (
              <span className="absolute -right-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-ink text-[10px] text-bone">
                {wishCount}
              </span>
            )}
          </Link>
          <button onClick={() => setDrawer(true)} className="relative" aria-label="Cart">
            <ShoppingBag className="h-5 w-5" strokeWidth={1.4} />
            {count > 0 && (
              <span className="absolute -right-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-ink text-[10px] text-bone">
                {count}
              </span>
            )}
          </button>
        </div>
      </nav>
    </motion.header>
  );
}
