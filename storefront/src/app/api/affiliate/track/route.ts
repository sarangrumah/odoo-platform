import { NextRequest, NextResponse } from "next/server";
import { odooRawFetch } from "@/lib/odoo";

export const dynamic = "force-dynamic";

/**
 * BFF proxy for affiliate click tracking:
 *   browser → /api/affiliate/track?...  ⇒  Odoo /affiliate/track?...
 * Tenant header is injected server-side (odooRawFetch).
 */
export async function GET(req: NextRequest) {
  try {
    const upstream = await odooRawFetch("affiliate/track", req.nextUrl.search);
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
    });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 502 });
  }
}
