"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import type { Product } from "@/lib/types";
import { imageUrl } from "@/lib/client";
import { formatPrice } from "@/lib/format";
import { WishlistButton } from "./WishlistButton";

export function ProductCard({ product, index = 0 }: { product: Product; index?: number }) {
  const src = imageUrl(product.image);
  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.6, delay: (index % 4) * 0.06, ease: [0.22, 1, 0.36, 1] }}
    >
      <Link href={`/products/${product.id}`} className="group block">
        <div className="relative aspect-[3/4] overflow-hidden bg-sand">
          {src ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={src}
              alt={product.name}
              className="h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
              loading="lazy"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-ink/30">
              <span className="font-editorial text-sm tracking-widest">{product.name}</span>
            </div>
          )}
          <div className="absolute left-3 top-3 flex flex-col gap-2">
            {!product.in_stock ? (
              <span className="bg-ink/80 px-2 py-1 text-[10px] uppercase tracking-widest text-bone">
                Sold out
              </span>
            ) : product.is_new ? (
              <span className="bg-ink px-2 py-1 text-[10px] uppercase tracking-widest text-bone">
                New
              </span>
            ) : null}
            {product.discount_pct ? (
              <span className="bg-accent px-2 py-1 text-[10px] font-medium uppercase tracking-widest text-bone">
                −{product.discount_pct}%
              </span>
            ) : null}
          </div>
          <WishlistButton
            productId={product.id}
            className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-bone/80 backdrop-blur-sm"
          />
        </div>
        <div className="mt-3 flex items-baseline justify-between gap-2">
          <h3 className="text-sm tracking-wide text-ink/90">{product.name}</h3>
          <span className="flex items-baseline gap-2 text-sm">
            {product.compare_at ? (
              <span className="text-ink/40 line-through">
                {formatPrice(product.compare_at, product.currency)}
              </span>
            ) : null}
            <span className={product.compare_at ? "text-accent" : "text-ink/60"}>
              {formatPrice(product.price, product.currency)}
            </span>
          </span>
        </div>
      </Link>
    </motion.div>
  );
}
