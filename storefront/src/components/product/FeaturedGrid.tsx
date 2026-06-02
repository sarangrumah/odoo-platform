"use client";

import { useEffect, useState } from "react";
import { ProductCard } from "./ProductCard";
import { fetchProducts } from "@/lib/client";
import type { Product } from "@/lib/types";

export function FeaturedGrid({
  limit = 8,
  sort = "newest",
  category,
}: {
  limit?: number;
  sort?: string;
  category?: number | string;
} = {}) {
  const [items, setItems] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params: Record<string, string | number> = { limit, sort };
    if (category) params.category = category;
    fetchProducts(params)
      .then((page) => setItems(page.items))
      .catch((e) => setError(String(e)));
  }, [limit, sort, category]);

  if (error) {
    return <p className="py-10 text-center text-sm text-ink/40">Catalog unavailable. {error}</p>;
  }
  if (!items.length) {
    return (
      <div className="grid grid-cols-2 gap-x-6 gap-y-10 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="aspect-[3/4] animate-pulse bg-sand" />
        ))}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-10 md:grid-cols-4">
      {items.map((p, i) => (
        <ProductCard key={p.id} product={p} index={i} />
      ))}
    </div>
  );
}
