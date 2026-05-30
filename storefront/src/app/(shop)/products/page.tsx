"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { ProductCard } from "@/components/product/ProductCard";
import { fetchProducts, fetchCategories, fetchTags, fetchContent, imageUrl } from "@/lib/client";
import { useLocale } from "@/store/locale-store";
import type { Product, ProductCategory, ProductTag, ContentBlock } from "@/lib/types";

const SORTS = [
  { key: "newest", label: "Newest" },
  { key: "price_asc", label: "Price ↑" },
  { key: "price_desc", label: "Price ↓" },
  { key: "name", label: "A–Z" },
];

export default function ProductsPage() {
  const [items, setItems] = useState<Product[]>([]);
  const [cats, setCats] = useState<ProductCategory[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [sort, setSort] = useState("newest");
  const [category, setCategory] = useState<string>("");
  const [tags, setTags] = useState<ProductTag[]>([]);
  const [selectedTags, setSelectedTags] = useState<number[]>([]);
  const [priceMin, setPriceMin] = useState("");
  const [priceMax, setPriceMax] = useState("");
  const [minInput, setMinInput] = useState("");
  const [maxInput, setMaxInput] = useState("");
  const [bounds, setBounds] = useState<{ min: number; max: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const locale = useLocale((s) => s.locale);
  const t = useLocale((s) => s.t);
  const [promo, setPromo] = useState<ContentBlock | null>(null);

  // Initialise filters from the URL without useSearchParams (avoids the
  // Next.js prerender Suspense requirement on this client page).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("sort")) setSort(params.get("sort")!);
    if (params.get("category")) setCategory(params.get("category")!);
    const tag = params.get("tag");
    if (tag) setSelectedTags(tag.split(",").map(Number).filter(Boolean));
    const pmin = params.get("price_min");
    const pmax = params.get("price_max");
    if (pmin) { setPriceMin(pmin); setMinInput(pmin); }
    if (pmax) { setPriceMax(pmax); setMaxInput(pmax); }
  }, []);

  useEffect(() => {
    fetchCategories().then(setCats).catch(() => setCats([]));
    fetchTags().then(setTags).catch(() => setTags([]));
    fetchContent().then((c) => setPromo(c.plp_promo ?? null)).catch(() => setPromo(null));
  }, [locale]);

  function toggleTag(id: number) {
    setSelectedTags((prev) =>
      prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id],
    );
  }

  function applyPrice() {
    setPriceMin(minInput.trim());
    setPriceMax(maxInput.trim());
  }

  function clearPrice() {
    setMinInput("");
    setMaxInput("");
    setPriceMin("");
    setPriceMax("");
  }

  const load = useCallback(
    async (reset: boolean) => {
      setLoading(true);
      try {
        const p = reset ? 1 : page;
        const params: Record<string, string | number> = { page: p, limit: 12, sort };
        if (category) params.category = category;
        if (selectedTags.length) params.tag = selectedTags.join(",");
        if (priceMin) params.price_min = priceMin;
        if (priceMax) params.price_max = priceMax;
        const res = await fetchProducts(params);
        setPages(res.pages);
        setItems((prev) => (reset ? res.items : [...prev, ...res.items]));
        setPage(p);
        if (res.price_bounds) setBounds(res.price_bounds);
      } finally {
        setLoading(false);
      }
    },
    [page, sort, category, selectedTags, priceMin, priceMax, locale],
  );

  useEffect(() => {
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sort, category, selectedTags, priceMin, priceMax, locale]);

  return (
    <div className="mx-auto max-w-7xl px-6 py-10">
      {promo && (promo.headline || promo.image) && (
        <div className="relative mb-10 overflow-hidden bg-ink text-bone">
          {promo.image && (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imageUrl(promo.image)} alt="" className="absolute inset-0 h-full w-full object-cover opacity-40" />
              <div className="absolute inset-0 bg-gradient-to-r from-ink/80 to-ink/20" />
            </>
          )}
          <div className="relative flex flex-col items-start gap-3 px-8 py-12 md:px-12">
            {promo.eyebrow && <p className="text-[11px] uppercase tracking-[0.22em] text-bone/70">{promo.eyebrow}</p>}
            <h2 className="font-editorial text-3xl md:text-4xl">{promo.headline}</h2>
            {promo.body && <p className="max-w-md text-sm text-bone/80">{promo.body}</p>}
            {promo.cta_label && (
              <Link href={promo.cta_url || "/products"} className="mt-2 border border-bone px-7 py-3 text-[11px] uppercase tracking-[0.2em] transition-colors hover:bg-bone hover:text-ink">
                {promo.cta_label}
              </Link>
            )}
          </div>
        </div>
      )}

      <div className="mb-10 flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-editorial text-4xl">{t("plp.title")}</h1>
        <div className="flex flex-wrap items-center gap-4 text-xs uppercase tracking-[0.16em]">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="border border-ink/20 bg-transparent px-3 py-2"
          >
            <option value="">{t("plp.all")}</option>
            {cats.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="border border-ink/20 bg-transparent px-3 py-2"
          >
            {SORTS.map((s) => (
              <option key={s.key} value={s.key}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>

      {tags.length > 0 && (
        <div className="mb-10 flex flex-wrap items-center gap-2">
          {tags.map((t) => {
            const on = selectedTags.includes(t.id);
            return (
              <button
                key={t.id}
                onClick={() => toggleTag(t.id)}
                className={`border px-4 py-2 text-[11px] uppercase tracking-[0.16em] transition-colors ${
                  on
                    ? "border-ink bg-ink text-bone"
                    : "border-ink/20 text-ink/70 hover:border-ink"
                }`}
              >
                {t.name}
              </button>
            );
          })}
          {selectedTags.length > 0 && (
            <button
              onClick={() => setSelectedTags([])}
              className="px-3 py-2 text-[11px] uppercase tracking-[0.16em] text-ink/40 underline hover:text-accent"
            >
              Reset
            </button>
          )}
        </div>
      )}

      <div className="mb-12 flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.16em]">
        <span className="text-ink/50">{t("plp.price")}</span>
        <input
          type="number"
          inputMode="numeric"
          value={minInput}
          min={0}
          placeholder={bounds ? String(Math.floor(bounds.min)) : "Min"}
          onChange={(e) => setMinInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && applyPrice()}
          className="w-32 border border-ink/20 bg-transparent px-3 py-2"
          aria-label="Harga minimum"
        />
        <span className="text-ink/40">—</span>
        <input
          type="number"
          inputMode="numeric"
          value={maxInput}
          min={0}
          placeholder={bounds ? String(Math.ceil(bounds.max)) : "Max"}
          onChange={(e) => setMaxInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && applyPrice()}
          className="w-32 border border-ink/20 bg-transparent px-3 py-2"
          aria-label="Harga maksimum"
        />
        <button
          onClick={applyPrice}
          className="border border-ink px-5 py-2 transition-colors hover:bg-ink hover:text-bone"
        >
          {t("plp.apply")}
        </button>
        {(priceMin || priceMax) && (
          <button
            onClick={clearPrice}
            className="px-3 py-2 text-ink/40 underline hover:text-accent"
          >
            {t("plp.reset")}
          </button>
        )}
      </div>

      {items.length === 0 && !loading ? (
        <p className="py-20 text-center text-sm text-ink/40">{t("plp.empty")}</p>
      ) : (
        <div className="grid grid-cols-2 gap-x-6 gap-y-12 md:grid-cols-4">
          {items.map((p, i) => (
            <ProductCard key={`${p.id}-${i}`} product={p} index={i} />
          ))}
        </div>
      )}

      {page < pages && (
        <div className="mt-16 text-center">
          <button
            disabled={loading}
            onClick={() => {
              setPage((p) => p + 1);
              setTimeout(() => load(false), 0);
            }}
            className="border border-ink px-10 py-4 text-xs uppercase tracking-[0.2em] transition-colors hover:bg-ink hover:text-bone disabled:opacity-50"
          >
            {loading ? t("common.loading") : t("plp.loadMore")}
          </button>
        </div>
      )}
    </div>
  );
}
