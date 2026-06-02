import { NextRequest, NextResponse } from "next/server";
import { odooRawFetch } from "@/lib/odoo";

export const dynamic = "force-dynamic";

/**
 * Public document download proxy: browser → /api/docs/<id>  ⇒  Odoo
 * /web/content/<id>?download=true (tenant header injected server-side). Only
 * serves PUBLIC PDF attachments — Odoo returns 404 for non-public ids to an
 * unauthenticated request, and we additionally require an application/pdf
 * response, so this can't relay arbitrary content (anti-SSRF).
 */
export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) {
    return NextResponse.json({ ok: false, error: "Bad id" }, { status: 400 });
  }
  try {
    const upstream = await odooRawFetch(`web/content/${id}`, "download=true");
    const ct = upstream.headers.get("content-type") || "";
    if (!upstream.ok || !ct.includes("application/pdf")) {
      return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });
    }
    const buf = await upstream.arrayBuffer();
    return new NextResponse(buf, {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": upstream.headers.get("content-disposition") || "attachment",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=300",
      },
    });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 502 });
  }
}
