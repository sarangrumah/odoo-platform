import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'Platform Onboarding',
  description: 'Onboard a new vertical onto the Odoo multi-tenant platform.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        <header className="border-b">
          <div className="container flex h-16 items-center justify-between">
            <Link href="/" className="font-semibold text-lg">
              Platform Onboarding
            </Link>
            <nav className="flex gap-6 text-sm">
              <Link href="/" className="hover:underline">
                Home
              </Link>
              <Link href="/intake" className="hover:underline">
                Onboard Vertical
              </Link>
            </nav>
          </div>
        </header>
        <main className="container py-10">{children}</main>
        <footer className="border-t mt-20">
          <div className="container py-6 text-sm text-muted-foreground">
            © {new Date().getFullYear()} Platform Hub. All rights reserved.
          </div>
        </footer>
      </body>
    </html>
  );
}
