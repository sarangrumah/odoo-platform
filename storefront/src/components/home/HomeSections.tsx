"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FadeIn } from "@/components/motion/FadeIn";
import { FeaturedGrid } from "@/components/product/FeaturedGrid";
import { CategoryTiles } from "@/components/home/CategoryTiles";
import { HeroCanvas } from "@/components/three/HeroCanvas";
import { Newsletter } from "@/components/home/Newsletter";
import { fetchContent, imageUrl } from "@/lib/client";
import { useLocale } from "@/store/locale-store";
import type { ContentBlock, SiteContent } from "@/lib/types";

const EMPTY: ContentBlock = {
  code: "",
  eyebrow: "",
  headline: "",
  body: "",
  cta_label: "",
  cta_url: "/products",
  image: null,
};

/** Image-left / text-right editorial split (set `reverse` to mirror it). */
function EditorialSplit({ block, reverse = false }: { block: ContentBlock; reverse?: boolean }) {
  if (!block.headline && !block.image) return null;
  return (
    <section className="mx-auto grid max-w-7xl gap-12 px-6 py-24 md:grid-cols-2 md:items-center">
      <FadeIn>
        {block.image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imageUrl(block.image)}
            alt=""
            className={`aspect-[4/5] w-full object-cover ${reverse ? "md:order-2" : ""}`}
          />
        ) : (
          <div className={`aspect-[4/5] bg-sand ${reverse ? "md:order-2" : ""}`} />
        )}
      </FadeIn>
      <FadeIn delay={0.1}>
        {block.eyebrow && <p className="eyebrow mb-4">{block.eyebrow}</p>}
        <h2 className="font-editorial text-3xl leading-snug md:text-4xl">{block.headline}</h2>
        {block.body && <p className="mt-6 max-w-md leading-relaxed text-ink/60">{block.body}</p>}
        {block.cta_label && (
          <Link
            href={block.cta_url || "/products"}
            className="mt-8 inline-block border border-ink px-8 py-3 text-xs uppercase tracking-[0.2em] transition-colors hover:bg-ink hover:text-bone"
          >
            {block.cta_label}
          </Link>
        )}
      </FadeIn>
    </section>
  );
}

export function HomeSections() {
  const locale = useLocale((s) => s.locale);
  const t = useLocale((s) => s.t);
  const [content, setContent] = useState<SiteContent>({});

  useEffect(() => {
    fetchContent().then(setContent).catch(() => setContent({}));
  }, [locale]);

  const hero = content.hero ?? EMPTY;
  const editorial = content.editorial ?? EMPTY;
  const lookbook = content.lookbook ?? EMPTY;
  const editorial2 = content.editorial_2 ?? EMPTY;
  const featured = content.featured ?? { ...EMPTY, headline: "New In", cta_label: "View all" };
  const collections = [content.collection_1, content.collection_2, content.collection_3].filter(
    (b): b is ContentBlock => !!b && !!b.headline,
  );
  const newsletter = content.newsletter;

  return (
    <div>
      {/* Hero — 3D animated canvas background + CMS copy */}
      <section className="relative flex min-h-[88vh] items-center overflow-hidden">
        <div className="absolute inset-0 -z-10 opacity-90">
          <HeroCanvas />
        </div>
        <div className="mx-auto max-w-7xl px-6">
          <FadeIn>
            {hero.eyebrow && <p className="eyebrow mb-6">{hero.eyebrow}</p>}
            <h1 className="font-editorial text-5xl leading-[1.05] tracking-tight md:text-7xl">
              {hero.headline || "The quiet confidence of fewer, better things."}
            </h1>
            <Link
              href={hero.cta_url || "/products"}
              className="mt-10 inline-block border border-ink px-10 py-4 text-xs uppercase tracking-[0.2em] transition-colors hover:bg-ink hover:text-bone"
            >
              {hero.cta_label || "Explore the collection"}
            </Link>
          </FadeIn>
        </div>
      </section>

      {/* Featured products — front-loaded so the catalog leads the page */}
      <section className="mx-auto max-w-7xl px-6 pb-6 pt-16">
        <FadeIn>
          <div className="mb-10 flex items-end justify-between">
            <h2 className="font-editorial text-3xl md:text-4xl">{featured.headline || t("home.newIn")}</h2>
            <Link href={featured.cta_url || "/products?sort=newest"} className="text-xs uppercase tracking-[0.2em] text-accent">
              {featured.cta_label || t("home.viewAll")}
            </Link>
          </div>
        </FadeIn>
        <FeaturedGrid limit={8} sort="newest" />
      </section>

      {/* Shop by category — product-led entry points into the PLP */}
      <section className="mx-auto max-w-7xl px-6 py-16">
        <FadeIn>
          <h2 className="mb-10 font-editorial text-3xl md:text-4xl">{t("home.shopByCategory")}</h2>
        </FadeIn>
        <CategoryTiles />
      </section>

      {/* Editorial split — CMS image + copy */}
      <EditorialSplit block={editorial} />

      {/* Lookbook — full-bleed campaign banner */}
      {(lookbook.image || lookbook.headline) && (
        <section className="relative my-8 flex min-h-[60vh] items-center justify-center overflow-hidden">
          {lookbook.image && (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imageUrl(lookbook.image)} alt="" className="absolute inset-0 h-full w-full object-cover" />
              <div className="absolute inset-0 bg-ink/35" />
            </>
          )}
          <FadeIn>
            <div className="relative px-6 text-center text-bone">
              {lookbook.eyebrow && <p className="text-[11px] uppercase tracking-[0.24em] text-bone/80">{lookbook.eyebrow}</p>}
              <h2 className="mt-3 font-editorial text-4xl md:text-5xl">{lookbook.headline}</h2>
              {lookbook.body && <p className="mx-auto mt-4 max-w-xl text-sm text-bone/85">{lookbook.body}</p>}
              {lookbook.cta_label && (
                <Link
                  href={lookbook.cta_url || "/products"}
                  className="mt-8 inline-block border border-bone px-9 py-3.5 text-xs uppercase tracking-[0.2em] transition-colors hover:bg-bone hover:text-ink"
                >
                  {lookbook.cta_label}
                </Link>
              )}
            </div>
          </FadeIn>
        </section>
      )}

      {/* Collections trio — CMS image tiles */}
      {collections.length > 0 && (
        <section className="mx-auto max-w-7xl px-6 py-24">
          <FadeIn>
            <h2 className="mb-10 font-editorial text-3xl">{t("home.collections")}</h2>
          </FadeIn>
          <div className="grid gap-6 md:grid-cols-3">
            {collections.map((c, i) => (
              <FadeIn key={c.code} delay={i * 0.08}>
                <Link href={c.cta_url || "/products"} className="group block">
                  <div className="relative aspect-[3/4] overflow-hidden bg-sand">
                    {c.image && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={imageUrl(c.image)}
                        alt={c.headline}
                        className="h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
                      />
                    )}
                    <div className="absolute inset-0 flex items-end bg-gradient-to-t from-ink/50 to-transparent p-6">
                      <h3 className="font-editorial text-2xl text-bone">{c.headline}</h3>
                    </div>
                  </div>
                </Link>
              </FadeIn>
            ))}
          </div>
        </section>
      )}

      {/* Second editorial split — reversed for rhythm */}
      <EditorialSplit block={editorial2} reverse />

      {/* Newsletter signup */}
      {newsletter && <Newsletter block={newsletter} />}
    </div>
  );
}
