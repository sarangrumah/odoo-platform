import type { Metadata } from "next";
import { headers } from "next/headers";
import { getProductServer } from "@/lib/odoo";
import ProductDetailClient from "./ProductDetailClient";

const SITE = process.env.NEXT_PUBLIC_SITE_NAME || "Gentlewoman";
const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://192.168.3.140:8443").replace(/\/$/, "");

/**
 * Server-rendered Open Graph / Twitter metadata so shared product links
 * (incl. affiliate `?aff=` links) render a rich preview card. The interactive
 * UI stays in the client component below.
 */
export async function generateMetadata({ params }: { params: { id: string } }): Promise<Metadata> {
  const locale = headers().get("x-locale") || "id";
  const product = await getProductServer(params.id, locale);
  if (!product) {
    return { title: `${SITE} — Considered Essentials` };
  }
  const title = `${product.name} — ${SITE}`;
  const description = (product.summary || product.name || "").toString().slice(0, 200);
  const url = `${SITE_URL}/products/${params.id}`;
  const image = `${SITE_URL}/api/img/web/image/product.template/${params.id}/image_1024`;
  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      type: "website",
      siteName: SITE,
      title,
      description,
      url,
      images: [{ url: image, width: 1024, height: 1024, alt: product.name }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [image],
    },
  };
}

export default function ProductDetailPage() {
  return <ProductDetailClient />;
}
