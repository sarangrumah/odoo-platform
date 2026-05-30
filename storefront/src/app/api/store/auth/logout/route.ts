import { NextRequest, NextResponse } from "next/server";
import { odooFetch } from "@/lib/odoo";
import { AT, clearAuthCookies, openToken } from "@/lib/session";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  // Best-effort: revoke the session server-side, then always clear the cookies.
  const at = openToken(req.cookies.get(AT)?.value);
  if (at) {
    try {
      await odooFetch("auth/logout", { method: "POST", authorization: `Bearer ${at}`, body: "{}" });
    } catch {
      /* ignore — cookies are cleared regardless */
    }
  }
  const res = NextResponse.json({ ok: true });
  clearAuthCookies(res);
  return res;
}
