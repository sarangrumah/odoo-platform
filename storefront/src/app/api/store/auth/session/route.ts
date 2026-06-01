import { NextRequest, NextResponse } from "next/server";
import { odooFetch } from "@/lib/odoo";
import { AT, RT, openToken, setAuthCookies, clearAuthCookies } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Authoritative session probe. The browser cannot read the HttpOnly auth
 * cookies, so it can't tell a live session from a stale persisted profile (e.g.
 * a `customer` left in localStorage after a server reset). This endpoint asks
 * the server — the only place that holds the cookies — and ALWAYS answers 200
 * with `{ authenticated, customer? }`. Returning 200 (never 401) is the whole
 * point: a logged-out probe must not show up as a red 401 in the console, and
 * it lets the client reconcile its persisted state without firing authed calls
 * (wishlist/cart) against a dead session first.
 */
export async function GET(req: NextRequest) {
  const at = openToken(req.cookies.get(AT)?.value);
  const rt = openToken(req.cookies.get(RT)?.value);

  if (!at && !rt) {
    const res = NextResponse.json({ ok: true, data: { authenticated: false } });
    clearAuthCookies(res); // tidy up any half-set/expired cookie pair
    return res;
  }

  const authFor = (token?: string | null) => (token ? `Bearer ${token}` : null);

  let upstream: Response | null = null;
  try {
    upstream = await odooFetch("customer/me", { method: "GET", authorization: authFor(at) });
  } catch {
    upstream = null;
  }

  // Transparent refresh on expiry, mirroring the BFF proxy.
  let rotated: { access: string; refresh?: string } | null = null;
  if ((!upstream || upstream.status === 401) && rt) {
    try {
      const r = await odooFetch("auth/refresh", { method: "POST", body: JSON.stringify({ refresh: rt }) });
      const rj = await r.json().catch(() => null);
      if (r.ok && rj?.ok) {
        rotated = { access: rj.data.access, refresh: rj.data.refresh };
        upstream = await odooFetch("customer/me", { method: "GET", authorization: authFor(rotated.access) });
      }
    } catch {
      /* fall through as unauthenticated */
    }
  }

  if (upstream && upstream.ok) {
    const json = await upstream.json().catch(() => null);
    if (json?.ok && json.data?.customer) {
      const res = NextResponse.json({
        ok: true,
        data: { authenticated: true, customer: json.data.customer },
      });
      if (rotated) setAuthCookies(res, rotated);
      return res;
    }
  }

  // No valid session: report logged-out and clear the dead cookies.
  const res = NextResponse.json({ ok: true, data: { authenticated: false } });
  clearAuthCookies(res);
  return res;
}
