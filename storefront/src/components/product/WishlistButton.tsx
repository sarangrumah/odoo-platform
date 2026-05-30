"use client";

import { useRouter } from "next/navigation";
import { Heart } from "lucide-react";
import { useWishlist } from "@/store/wishlist-store";
import { useAuth } from "@/store/auth-store";

/**
 * Heart toggle. Wishlist lives in Odoo (`custom.wishlist`) and requires a
 * logged-in customer, so an anonymous click routes to login (same pattern as
 * add-to-cart). Used inside <Link> cards — clicks are stopped from navigating.
 */
export function WishlistButton({
  productId,
  className = "",
}: {
  productId: number;
  className?: string;
}) {
  const router = useRouter();
  const customer = useAuth((s) => s.customer);
  const wished = useWishlist((s) => s.ids.includes(productId));
  const toggle = useWishlist((s) => s.toggle);

  async function onClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!customer) return router.push("/account/login");
    try {
      await toggle(productId);
    } catch {
      router.push("/account/login");
    }
  }

  return (
    <button
      onClick={onClick}
      aria-label={wished ? "Remove from wishlist" : "Add to wishlist"}
      aria-pressed={wished}
      className={`transition-colors ${wished ? "text-accent" : "text-ink/60 hover:text-accent"} ${className}`}
    >
      <Heart className="h-5 w-5" strokeWidth={1.4} fill={wished ? "currentColor" : "none"} />
    </button>
  );
}
