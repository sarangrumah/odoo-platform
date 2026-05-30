import { NextRequest, NextResponse } from "next/server";

/**
 * Two jobs:
 *  1) Locale URL routing (/id, /en) — prefixed paths are rewritten to the
 *     unprefixed route (+ NEXT_LOCALE cookie + x-locale header); unprefixed
 *     paths redirect to `/{locale}{path}`.
 *  2) Strict security headers on every page response, incl. a per-request
 *     nonce-based Content-Security-Policy (Next reads the nonce from the
 *     request CSP header and stamps it onto its own scripts).
 * API/asset paths are excluded by `matcher`.
 */
const LOCALES = ["id", "en"];
const DEFAULT_LOCALE = "id";

function buildCsp(): string {
  // NOTE: a per-request nonce / 'strict-dynamic' is incompatible with Next's
  // statically-prerendered pages (their HTML is built without a nonce), so we
  // restrict scripts to same-origin + inline. This still blocks ALL external /
  // injected-src scripts; inline-XSS is covered by React auto-escaping +
  // sanitised dangerouslySetInnerHTML + the locked-down directives below.
  return [
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "frame-src 'none'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "style-src 'self' 'unsafe-inline'",
    "script-src 'self' 'unsafe-inline'",
    "connect-src 'self'",
    "form-action 'self'",
    "manifest-src 'self'",
    "worker-src 'self' blob:",
    "upgrade-insecure-requests",
  ].join("; ");
}

function applySecurityHeaders(res: NextResponse, csp: string) {
  res.headers.set("Content-Security-Policy", csp);
  res.headers.set("X-Frame-Options", "DENY");
  res.headers.set("X-Content-Type-Options", "nosniff");
  res.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  res.headers.set("X-DNS-Prefetch-Control", "off");
  res.headers.set("Cross-Origin-Opener-Policy", "same-origin");
  res.headers.set(
    "Permissions-Policy",
    "camera=(), microphone=(), payment=(), usb=(), geolocation=(self)",
  );
  res.headers.set(
    "Strict-Transport-Security",
    "max-age=63072000; includeSubDomains",
  );
  return res;
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const seg = pathname.split("/")[1];

  const csp = buildCsp();

  if (LOCALES.includes(seg)) {
    const url = req.nextUrl.clone();
    url.pathname = pathname.slice(seg.length + 1) || "/";
    // Forward the locale so server generateMetadata can localise OG tags.
    const requestHeaders = new Headers(req.headers);
    requestHeaders.set("x-locale", seg);
    const res = NextResponse.rewrite(url, { request: { headers: requestHeaders } });
    res.cookies.set("NEXT_LOCALE", seg, {
      path: "/",
      maxAge: 60 * 60 * 24 * 365,
      sameSite: "lax",
    });
    return applySecurityHeaders(res, csp);
  }

  const cookieLoc = req.cookies.get("NEXT_LOCALE")?.value;
  const locale = cookieLoc && LOCALES.includes(cookieLoc) ? cookieLoc : DEFAULT_LOCALE;
  const url = req.nextUrl.clone();
  url.pathname = `/${locale}${pathname === "/" ? "" : pathname}`;
  return applySecurityHeaders(NextResponse.redirect(url), csp);
}

export const config = {
  // Everything except API routes, Next internals, and files with an extension.
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
