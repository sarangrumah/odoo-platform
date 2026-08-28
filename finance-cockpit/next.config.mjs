/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Caddy fronts this at /finance with `handle` (not `handle_path`), so the app
  // has to see the prefix itself — same arrangement as sales-cockpit.
  basePath: "/finance",
  reactStrictMode: true,
  poweredByHeader: false,
  eslint: { ignoreDuringBuilds: true },
  // `pg` is a native-ish driver; keep it out of the bundler's hands.
  serverExternalPackages: ["pg"],
};

export default nextConfig;
