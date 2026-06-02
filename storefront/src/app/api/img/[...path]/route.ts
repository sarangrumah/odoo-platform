import { NextRequest, NextResponse } from "next/server";
import { odooRawFetch } from "@/lib/odoo";

export const dynamic = "force-dynamic";

/**
 * Image proxy: browser → /api/img/web/image/...  ⇒  Odoo /web/image/... with
 * the tenant X-Odoo-Database header. Lets <img> tags load product imagery from
 * the storefront's own origin — no hosts entry / CA trust on the client needed.
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const path = (await params).path.join("/");
  // Lock the proxy to Odoo's public image endpoint only — never relay arbitrary
  // Odoo paths (SSRF / open-proxy), and reject path traversal.
  if (!/^web\/image\//.test(path) || path.includes("..")) {
    return NextResponse.json({ ok: false, error: "Forbidden" }, { status: 403 });
  }
  try {
    const upstream = await odooRawFetch(path, req.nextUrl.search);
    const buf = await upstream.arrayBuffer();
    const ct = upstream.headers.get("content-type") || "image/jpeg";
    // Only ever return image bytes from this endpoint.
    if (!ct.startsWith("image/")) {
      return NextResponse.json({ ok: false, error: "Not an image" }, { status: 415 });
    }
    return new NextResponse(buf, {
      status: upstream.status,
      headers: {
        "Content-Type": ct,
        "Cache-Control": "public, max-age=3600",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 502 });
  }
}
