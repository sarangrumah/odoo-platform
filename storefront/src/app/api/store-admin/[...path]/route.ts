import { NextRequest, NextResponse } from "next/server";
import { odooAdminFetch } from "@/lib/odoo";

export const dynamic = "force-dynamic";

/**
 * BFF proxy for HMAC-signed server-to-server admin endpoints.
 * Browser → /api/store-admin/<path>  ⇒  Odoo → /storefront/api/admin/<path>
 * The HMAC secret lives only here; the browser can trigger these but never
 * sees the signing key. Useful for cache warming / authoritative status.
 */
async function proxy(req: NextRequest, path: string[]) {
  const target = path.join("/");
  let payload: unknown = {};
  if (req.method !== "GET") {
    const text = await req.text();
    payload = text ? JSON.parse(text) : {};
  }
  try {
    const upstream = await odooAdminFetch(target, payload);
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error_code: "ADMIN_PROXY_FAILED", message: String(e) },
      { status: 502 },
    );
  }
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path);
}
export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path);
}
