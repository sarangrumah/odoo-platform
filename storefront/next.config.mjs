/** @type {import('next').NextConfig} */
const odooPublic = process.env.NEXT_PUBLIC_ODOO_PUBLIC_URL || "";

const remotePatterns = [];
if (odooPublic) {
  try {
    const u = new URL(odooPublic);
    remotePatterns.push({
      protocol: u.protocol.replace(":", ""),
      hostname: u.hostname,
      port: u.port || "",
      pathname: "/web/image/**",
    });
  } catch {
    // ignore malformed URL — falls back to no remote images
  }
}

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  images: {
    remotePatterns,
    // Odoo placeholder images can be large; allow long cache.
    minimumCacheTTL: 3600,
  },
  // The 3D bundle (three.js) is heavy; keep it out of the server bundle.
  transpilePackages: ["three"],
};

export default nextConfig;
