"use client";

// Navigation carries the current filter state across pages: an as-of date set
// on the AP page must still apply when you jump to Open Items, or the two pages
// quietly describe different days.

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const LINKS = [
  { href: "/ap", label: "Hutang & Pembayaran" },
  { href: "/openitems", label: "Open Items & GR/IR" },
  { href: "/pos", label: "Clearing POS & Bank" },
  { href: "/close", label: "Kesiapan Tutup Buku" },
  { href: "/actions", label: "Rekomendasi" },
  { href: "/tie", label: "Pembuktian Angka" },
];

export function Nav() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const qs = searchParams.toString();

  return (
    <nav className="nav">
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={qs ? `${link.href}?${qs}` : link.href}
          aria-current={pathname.startsWith(link.href) ? "page" : undefined}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
