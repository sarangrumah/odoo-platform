"use client";

import { useEffect, useState } from "react";
import { Instagram, Music2, Facebook, MessageCircle } from "lucide-react";
import { fetchContent } from "@/lib/client";
import { useLocale } from "@/store/locale-store";
import type { ContentBlock } from "@/lib/types";

const SITE = process.env.NEXT_PUBLIC_SITE_NAME || "Gentle Woman";
const DEFAULT_TAGLINE =
  "Considered essentials, made to last. Powered by Odoo commerce, delivered through a headless Next.js storefront.";

const SOCIALS = [
  { key: "ig", label: "Instagram", Icon: Instagram, href: process.env.NEXT_PUBLIC_SOCIAL_INSTAGRAM || "https://www.instagram.com/gentlewomanofficial/" },
  { key: "tt", label: "TikTok", Icon: Music2, href: process.env.NEXT_PUBLIC_SOCIAL_TIKTOK || "https://www.tiktok.com/@gentlewomanofficial" },
  { key: "fb", label: "Facebook", Icon: Facebook, href: process.env.NEXT_PUBLIC_SOCIAL_FACEBOOK || "https://www.facebook.com/gentlewomanofficial" },
  { key: "wa", label: "WhatsApp", Icon: MessageCircle, href: process.env.NEXT_PUBLIC_SOCIAL_WHATSAPP || "https://wa.me/6281234567890" },
];

export function Footer() {
  const locale = useLocale((s) => s.locale);
  const [footer, setFooter] = useState<ContentBlock | null>(null);

  useEffect(() => {
    fetchContent().then((c) => setFooter(c.footer ?? null)).catch(() => setFooter(null));
  }, [locale]);

  return (
    <footer className="mt-32 border-t border-ink/10 bg-sand/40">
      <div className="mx-auto grid max-w-7xl gap-10 px-6 py-16 md:grid-cols-4">
        <div className="md:col-span-2">
          <p className="font-editorial text-xl uppercase tracking-[0.3em]">{SITE}</p>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-ink/60">
            {footer?.body || DEFAULT_TAGLINE}
          </p>
          <div className="mt-6 flex gap-4">
            {SOCIALS.map(({ key, label, Icon, href }) => (
              <a
                key={key}
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={label}
                className="text-ink/60 transition-colors hover:text-accent"
              >
                <Icon className="h-5 w-5" strokeWidth={1.4} />
              </a>
            ))}
          </div>
        </div>
        <div className="text-sm">
          <p className="eyebrow mb-4">Shop</p>
          <ul className="space-y-2 text-ink/70">
            <li>New Arrivals</li>
            <li>Ready to Wear</li>
            <li>Accessories</li>
          </ul>
        </div>
        <div className="text-sm">
          <p className="eyebrow mb-4">Client Care</p>
          <ul className="space-y-2 text-ink/70">
            <li>Shipping &amp; Returns</li>
            <li>Track Order</li>
            <li>Contact</li>
          </ul>
        </div>
      </div>
      <div className="border-t border-ink/10 px-6 py-6 text-center text-[11px] uppercase tracking-[0.2em] text-ink/40">
        © {SITE} — demo storefront
      </div>
    </footer>
  );
}
