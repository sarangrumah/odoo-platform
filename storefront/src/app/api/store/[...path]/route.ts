import { NextRequest, NextResponse } from "next/server";
import { odooFetch } from "@/lib/odoo";
import { rateLimit, policyFor } from "@/lib/ratelimit";
import { AT, RT, setAuthCookies, openToken } from "@/lib/session";

export const dynamic = "force-dynamic";

const MAX_BODY = 64 * 1024; // 64 KB — storefront payloads are tiny

function clientIp(req: NextRequest): string {
  return (req.headers.get("x-forwarded-for") || "").split(",")[0].trim() || "unknown";
}

/**
 * BFF proxy for public + JWT storefront endpoints.
 * Browser → /api/store/<path>  ⇒  Odoo → /storefront/api/<path>
 *
 * Auth is injected SERVER-SIDE from the HttpOnly `gw_at` cookie (the browser
 * never sends a Bearer token). On a 401 the BFF transparently refreshes using
 * the `gw_rt` cookie, re-issues both cookies, and retries once.
 */
async function proxy(req: NextRequest, path: string[]) {
  const target = path.join("/");

  const policy = policyFor(target);
  if (policy && !rateLimit(`${clientIp(req)}:${target}`, policy.limit, policy.windowMs)) {
    return NextResponse.json(
      { ok: false, error_code: "RATE_LIMITED", message: "Too many requests. Please try again shortly." },
      { status: 429, headers: { "Retry-After": "60" } },
    );
  }

  const query = req.nextUrl.search.replace(/^\?/, "");
  let body: string | null = null;
  if (req.method !== "GET" && req.method !== "HEAD") {
    body = await req.text();
    if (body.length > MAX_BODY) {
      return NextResponse.json(
        { ok: false, error_code: "PAYLOAD_TOO_LARGE", message: "Request body too large." },
        { status: 413 },
      );
    }
  }

  const at = openToken(req.cookies.get(AT)?.value); // AES-GCM sealed in the cookie
  const rt = openToken(req.cookies.get(RT)?.value);
  const authFor = (token?: string | null) => (token ? `Bearer ${token}` : null);

  let upstream: Response;
  try {
    upstream = await odooFetch(target, { method: req.method, authorization: authFor(at), body, query });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error_code: "UPSTREAM_UNREACHABLE", message: String(e) },
      { status: 502 },
    );
  }

  // Transparent refresh on expiry.
  let rotated: { access: string; refresh?: string } | null = null;
  if (upstream.status === 401 && rt) {
    try {
      const r = await odooFetch("auth/refresh", { method: "POST", body: JSON.stringify({ refresh: rt }) });
      const rj = await r.json().catch(() => null);
      if (r.ok && rj?.ok) {
        rotated = { access: rj.data.access, refresh: rj.data.refresh };
        upstream = await odooFetch(target, {
          method: req.method,
          authorization: authFor(rotated.access),
          body,
          query,
        });
      }
    } catch {
      /* fall through with the original 401 */
    }
  }

  const text = await upstream.text();
  const res = new NextResponse(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
  });
  if (rotated) setAuthCookies(res, rotated);
  return res;
}

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path);
}
export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path);
}
export async function PUT(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path);
}
export async function DELETE(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path);
}
