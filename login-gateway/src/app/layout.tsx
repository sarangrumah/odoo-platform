import type { Metadata, Viewport } from "next";

import { asset } from "@/lib/url";

import "./globals.css";

export const metadata: Metadata = {
  title: "EAL-Hub — Masuk",
  // No version number: this description is served to every anonymous visitor
  // and to every crawler that indexes the login page.
  description: "Pintu masuk sistem ERP Erajaya Active Lifestyle",
  // basePath does not apply to a bare string here, same trap as <img src>.
  icons: { icon: [{ url: asset("/brand/favicon.svg"), type: "image/svg+xml" }] },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#eef1f5" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1119" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
