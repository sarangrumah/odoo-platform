/** @type {import('next').NextConfig} */
const nextConfig = {
  // Baked, read-only image: deploy is rebuild + recreate, same as vas-pmo.
  output: "standalone",
  // Shares the 443 listener with Odoo itself, so it lives under a path. Caddy
  // passes the prefix through untouched (`handle`, not `handle_path`).
  //
  // Note the app deliberately sends the browser OUTSIDE this prefix once the
  // session cookie is set (to /web/login, which is Odoo). That redirect is
  // built as an absolute URL in src/app/actions.ts precisely so basePath does
  // not get prepended to it.
  basePath: "/signin",
  reactStrictMode: true,
  poweredByHeader: false,
  eslint: { ignoreDuringBuilds: true },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          // This page is the one place a tenant list could leak into a cache.
          { key: "Cache-Control", value: "no-store" },
        ],
      },
    ];
  },
};

export default nextConfig;
