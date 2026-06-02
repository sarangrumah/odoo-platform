"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { motion } from "framer-motion";
import { Expand, Heart, MapPin, Ruler, Share2 } from "lucide-react";
import { fetchProduct, fetchAvailability, imageUrl } from "@/lib/client";
import { formatPrice } from "@/lib/format";
import { safeHtml } from "@/lib/sanitize";
import { useCart } from "@/store/cart-store";
import { useAuth } from "@/store/auth-store";
import { useWishlist } from "@/store/wishlist-store";
import { useLocale } from "@/store/locale-store";
import { ImageLightbox } from "@/components/product/ImageLightbox";
import { SizeGuide } from "@/components/product/SizeGuide";
import type { Product, StoreAvailability } from "@/lib/types";

const ProductViewer = dynamic(() => import("@/components/three/ProductViewer"), { ssr: false });

export default function ProductDetailClient() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [product, setProduct] = useState<Product | null>(null);
  const [availability, setAvailability] = useState<StoreAvailability[]>([]);
  const [active, setActive] = useState(0);
  const [view3d, setView3d] = useState(false);
  const [lightbox, setLightbox] = useState(false);
  const [sizeGuideOpen, setSizeGuideOpen] = useState(false);
  const [selectedVariant, setSelectedVariant] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const add = useCart((s) => s.add);
  const customer = useAuth((s) => s.customer);
  const toggleWishlist = useWishlist((s) => s.toggle);
  const wishedIds = useWishlist((s) => s.ids);
  const locale = useLocale((s) => s.locale);
  const t = useLocale((s) => s.t);

  useEffect(() => {
    setSelectedVariant(null);
    setActive(0);
    fetchProduct(id).then(setProduct).catch(() => setProduct(null));
    fetchAvailability(id).then(setAvailability).catch(() => setAvailability([]));
  }, [id, locale]);

  async function handleShare() {
    const url = typeof window !== "undefined" ? window.location.href : "";
    const data = { title: product?.name, text: product?.name, url };
    try {
      if (navigator.share) await navigator.share(data);
      else {
        await navigator.clipboard.writeText(url);
        alert("Link disalin ke clipboard");
      }
    } catch {
      /* user dismissed the share sheet — ignore */
    }
  }

  if (!product) {
    return <div className="mx-auto max-w-7xl px-6 py-20 text-center text-ink/40">Loading…</div>;
  }

  const gallery = product.images?.length ? product.images : [product.image];
  const wished = wishedIds.includes(product.id);
  const sizes = product.variants && product.variants.length > 1 ? product.variants : [];
  const hasSizes = sizes.length > 0;
  const chosen = hasSizes ? sizes.find((v) => v.id === selectedVariant) ?? null : null;
  // What "Add to cart" acts on: the chosen size variant, else the product itself.
  const buyable = hasSizes ? !!chosen && chosen.in_stock : product.in_stock;

  async function handleAdd() {
    if (!customer) return router.push("/account/login");
    if (hasSizes && !chosen) return; // must pick a size first
    setBusy(true);
    try {
      await add(hasSizes ? chosen!.id : product!.id, 1);
    } catch {
      router.push("/account/login");
    } finally {
      setBusy(false);
    }
  }

  function addLabel() {
    if (hasSizes && !chosen) return t("pdp.selectSize");
    if (!buyable) return t("pdp.soldOut");
    return busy ? t("pdp.adding") : t("pdp.addToCart");
  }

  async function handleWishlist() {
    if (!customer) return router.push("/account/login");
    try {
      await toggleWishlist(product!.id);
    } catch {
      router.push("/account/login");
    }
  }

  return (
    <div className="mx-auto grid max-w-[1440px] gap-10 px-6 py-10 md:grid-cols-[1.4fr_1fr] md:items-start lg:gap-16">
      {/* Gallery / 3D */}
      <div>
        <div className="group relative aspect-[3/4] overflow-hidden bg-sand">
          {view3d ? (
            <ProductViewer image={imageUrl(gallery[active])} />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <motion.img
              key={active}
              src={imageUrl(gallery[active])}
              alt={product.name}
              onClick={() => setLightbox(true)}
              className="h-full w-full cursor-zoom-in object-cover"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5 }}
            />
          )}
          {!view3d && (
            <button
              onClick={() => setLightbox(true)}
              aria-label={t("pdp.zoom")}
              className="absolute left-4 top-4 flex items-center gap-2 bg-bone/80 px-3 py-2 text-[10px] uppercase tracking-[0.18em] text-ink opacity-0 transition-opacity group-hover:opacity-100"
            >
              <Expand className="h-3.5 w-3.5" strokeWidth={1.5} /> {t("pdp.zoom")}
            </button>
          )}
          <button
            onClick={() => setView3d((v) => !v)}
            className="absolute bottom-4 right-4 bg-ink/80 px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-bone"
          >
            {view3d ? "Photos" : "3D View"}
          </button>
        </div>
        {!view3d && gallery.length > 1 && (
          <div className="mt-4 grid grid-cols-5 gap-3">
            {gallery.map((g, i) => (
              <button
                key={i}
                onClick={() => setActive(i)}
                onDoubleClick={() => setLightbox(true)}
                className={`aspect-[3/4] overflow-hidden bg-sand transition-opacity hover:opacity-90 ${
                  i === active ? "ring-1 ring-ink ring-offset-2 ring-offset-bone" : "opacity-70"
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={imageUrl(g)} alt="" className="h-full w-full object-cover" />
              </button>
            ))}
          </div>
        )}
      </div>

      <ImageLightbox
        images={gallery}
        index={active}
        open={lightbox}
        alt={product.name}
        onClose={() => setLightbox(false)}
        onIndexChange={setActive}
      />

      {/* Detail */}
      <div className="md:sticky md:top-28 md:self-start md:pt-4">
        <p className="eyebrow mb-4">
          {product.categories.map((c) => c.name).join(" / ") || "Ready to Wear"}
        </p>
        <h1 className="font-editorial text-4xl leading-tight">{product.name}</h1>
        <div className="mt-4 flex items-center gap-3 text-lg">
          {product.compare_at ? (
            <span className="text-ink/40 line-through">
              {formatPrice(product.compare_at, product.currency)}
            </span>
          ) : null}
          <span className={product.compare_at ? "text-accent" : "text-ink/70"}>
            {formatPrice(product.price, product.currency)}
          </span>
          {product.discount_pct ? (
            <span className="bg-accent px-2 py-1 text-[11px] font-medium uppercase tracking-widest text-bone">
              −{product.discount_pct}%
            </span>
          ) : null}
          {product.is_new ? (
            <span className="bg-ink px-2 py-1 text-[11px] font-medium uppercase tracking-widest text-bone">
              New
            </span>
          ) : null}
        </div>
        {product.ref && (
          <p className="mt-1 text-xs uppercase tracking-[0.18em] text-ink/40">Ref. {product.ref}</p>
        )}

        {product.tags && product.tags.length > 0 && (
          <div className="mt-5 flex flex-wrap gap-2">
            {product.tags.map((tag) => (
              <span
                key={tag.id}
                className="border border-ink/20 px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-ink/60"
              >
                {tag.name}
              </span>
            ))}
          </div>
        )}

        {product.description && (
          <div
            className="prose prose-sm mt-8 max-w-none text-ink/70"
            dangerouslySetInnerHTML={{ __html: safeHtml(product.description) }}
          />
        )}

        {product.material && (
          <div className="mt-8 border-t border-ink/10 pt-6">
            <p className="eyebrow mb-2">{t("pdp.material")}</p>
            <p className="whitespace-pre-line text-sm text-ink/70">{product.material}</p>
          </div>
        )}

        {/* Size selector — pick a size before adding to cart */}
        {hasSizes && (
          <div className="mt-8">
            <div className="mb-3 flex items-center justify-between">
              <p className="eyebrow">{t("pdp.selectSize")}</p>
              <button
                onClick={() => setSizeGuideOpen(true)}
                className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.16em] text-ink/50 underline-offset-4 hover:text-accent hover:underline"
              >
                <Ruler className="h-3.5 w-3.5" strokeWidth={1.5} /> {t("pdp.sizeGuide")}
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {sizes.map((v) => {
                const label = v.attributes.map((a) => a.value).join(" · ") || `#${v.id}`;
                const isSel = v.id === selectedVariant;
                return (
                  <button
                    key={v.id}
                    onClick={() => setSelectedVariant(v.id)}
                    title={v.in_stock ? formatPrice(v.price, product.currency) : t("pdp.soldOut")}
                    className={`min-w-[3.25rem] border px-4 py-2.5 text-center text-sm transition-colors ${
                      isSel
                        ? "border-ink bg-ink text-bone"
                        : v.in_stock
                          ? "border-ink/30 text-ink hover:border-ink"
                          : "border-ink/10 text-ink/30 line-through"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <button
          onClick={handleAdd}
          disabled={busy || !buyable}
          className="mt-10 w-full bg-ink py-5 text-xs uppercase tracking-[0.25em] text-bone transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {addLabel()}
        </button>

        <button
          onClick={handleWishlist}
          className={`mt-3 flex w-full items-center justify-center gap-2 border py-4 text-xs uppercase tracking-[0.25em] transition-colors ${
            wished
              ? "border-accent text-accent"
              : "border-ink/30 text-ink hover:border-ink"
          }`}
        >
          <Heart className="h-4 w-4" strokeWidth={1.5} fill={wished ? "currentColor" : "none"} />
          {wished ? t("pdp.savedWishlist") : t("pdp.addWishlist")}
        </button>

        <button
          onClick={handleShare}
          className="mt-3 flex w-full items-center justify-center gap-2 py-3 text-[11px] uppercase tracking-[0.25em] text-ink/50 transition-colors hover:text-accent"
        >
          <Share2 className="h-4 w-4" strokeWidth={1.5} />
          {t("pdp.share")}
        </button>

        {availability.length > 0 && (
          <div className="mt-8 border-t border-ink/10 pt-6">
            <p className="eyebrow mb-3 flex items-center gap-2">
              <MapPin className="h-4 w-4" strokeWidth={1.5} /> {t("pdp.inStore")}
            </p>
            <ul className="space-y-2 text-sm">
              {availability.map((s) => (
                <li key={s.store_id} className="flex items-center justify-between gap-3">
                  <span className="text-ink/70">
                    {s.store_name.replace(/^Gentle\s?woman\s*—\s*/i, "")}
                    <span className="text-ink/40"> · {s.city}</span>
                  </span>
                  <span
                    className={
                      s.in_stock
                        ? "text-[11px] uppercase tracking-[0.16em] text-accent"
                        : "text-[11px] uppercase tracking-[0.16em] text-ink/30"
                    }
                  >
                    {s.in_stock ? `${t("pdp.available")} (${s.qty})` : t("pdp.outOfStock")}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[11px] text-ink/40">
              Stok real-time per toko — ambil di toko (click &amp; collect) segera hadir.
            </p>
          </div>
        )}

      </div>

      <SizeGuide open={sizeGuideOpen} onClose={() => setSizeGuideOpen(false)} />
    </div>
  );
}
