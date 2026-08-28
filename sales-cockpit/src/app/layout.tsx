import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Levi's Sales Cockpit",
  description: "Dasbor penjualan retail — prd_levis_begbal",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
