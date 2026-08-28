"use client";

// Navigation carries the current filter state across pages: switching from
// Overview to Stores while filtered to Grand Indonesia must stay filtered.

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const LINKS = [
  { href: "/overview", label: "Ringkasan" },
  { href: "/stores", label: "Toko" },
  { href: "/products", label: "Produk" },
  { href: "/associates", label: "Associate" },
  { href: "/actions", label: "Rekomendasi" },
  { href: "/trust", label: "Kualitas Data" },
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
          aria-current={pathname === link.href ? "page" : undefined}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
