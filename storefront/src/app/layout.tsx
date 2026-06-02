import type { Metadata } from "next";
import "./globals.css";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { AnnouncementBar } from "@/components/layout/AnnouncementBar";
import { MainShell } from "@/components/layout/MainShell";
import { CartDrawer } from "@/components/cart/CartDrawer";
import { CookieConsent } from "@/components/layout/CookieConsent";
import { AffiliateCapture } from "@/components/AffiliateCapture";
import { LocaleSync } from "@/components/LocaleSync";
import { StoreHydrator } from "@/components/StoreHydrator";
import { ShopperWidget } from "@/components/shopper";

const SITE = process.env.NEXT_PUBLIC_SITE_NAME || "Gentlewoman";
const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://192.168.3.140:8443").replace(/\/$/, "");

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: `${SITE} — Considered Essentials`,
  description: "A headless storefront powered by Odoo commerce.",
  openGraph: {
    type: "website",
    siteName: SITE,
    title: `${SITE} — Considered Essentials`,
    description: "A headless storefront powered by Odoo commerce.",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <AnnouncementBar />
        <Header />
        <CartDrawer />
        <MainShell>{children}</MainShell>
        <Footer />
        <CookieConsent />
        <ShopperWidget />
        <AffiliateCapture />
        <LocaleSync />
        <StoreHydrator />
      </body>
    </html>
  );
}
