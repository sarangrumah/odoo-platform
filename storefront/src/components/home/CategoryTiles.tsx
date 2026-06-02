"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FadeIn } from "@/components/motion/FadeIn";
import { fetchCategories, fetchProducts, imageUrl } from "@/lib/client";
import { useLocale } from "@/store/locale-store";

type Tile = { id: number; name: string; image: string | null };

/**
 * Top-level category tiles for the landing page. Each tile borrows the image of
 * a product in that category (falling back to a sand block) and links to the
 * filtered PLP — turning the category taxonomy into a product-led entry point.
 */
export function CategoryTiles() {
  const locale = useLocale((s) => s.locale);
  const [tiles, setTiles] = useState<Tile[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cats = await fetchCategories();
        const tops = cats.filter((c) => c.parent_id == null).slice(0, 4);
        const withImg = await Promise.all(
          tops.map(async (c) => {
            let image: string | null = null;
            try {
              const page = await fetchProducts({ category: c.id, limit: 1 });
              image = page.items[0]?.image ?? null;
            } catch {
              /* leave image null — tile falls back to a sand block */
            }
            return { id: c.id, name: c.name, image };
          }),
        );
        if (!cancelled) setTiles(withImg);
      } catch {
        if (!cancelled) setTiles([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [locale]);

  if (!tiles.length) return null;

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4 md:gap-6">
      {tiles.map((c, i) => (
        <FadeIn key={c.id} delay={i * 0.06}>
          <Link href={`/products?category=${c.id}`} className="group block">
            <div className="relative aspect-[3/4] overflow-hidden bg-sand">
              {c.image && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={imageUrl(c.image)}
                  alt={c.name}
                  className="h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
                />
              )}
              <div className="absolute inset-0 flex items-end bg-gradient-to-t from-ink/55 to-transparent p-5">
                <h3 className="font-editorial text-xl text-bone md:text-2xl">{c.name}</h3>
              </div>
            </div>
          </Link>
        </FadeIn>
      ))}
    </div>
  );
}
