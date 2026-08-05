/** @type {import('next').NextConfig} */
const nextConfig = {
  // Baked, read-only image: deploy is rebuild + recreate, same as the storefront.
  output: "standalone",
  // Published behind Caddy on the shared 443 listener, which has no spare hostname to give
  // this app -- DOMAIN is a bare IP. So it lives under a path instead, and Caddy passes the
  // prefix through untouched (`handle`, not `handle_path`): with basePath set, the app
  // expects to see /vaspmo itself. Everything downstream follows from this one line --
  // the container healthcheck, and custom_project_notify.bff_url, both gain the prefix.
  basePath: "/vaspmo",
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
        ],
      },
    ];
  },
};

export default nextConfig;
