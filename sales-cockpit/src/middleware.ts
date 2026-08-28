import { NextResponse, type NextRequest } from "next/server";

/**
 * Keep anonymous traffic off the app shell.
 *
 * Presence of the cookie only — the signature and expiry are verified
 * server-side in the layout, which is the actual boundary. Middleware runs on
 * the edge runtime where node:crypto is not available, so it cannot verify the
 * HMAC even if it wanted to.
 */
export function middleware(request: NextRequest) {
  if (request.cookies.has("cockpit_session")) return NextResponse.next();

  // The assistant is called by fetch, not by navigation: a 307 to /login would
  // arrive at the widget as an HTML page and read as a parse error. Say 401 and
  // let the client tell the reader their session expired.
  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  // basePath has to be written back in by hand: `nextUrl.pathname` arrives with
  // it stripped and `NextResponse.redirect` wants an absolute URL, so without
  // this an anonymous hit on /cockpit/overview would be sent to /login — which
  // the shared Caddy hands to Odoo, not to this app.
  const login = new URL(`${request.nextUrl.basePath}/login`, request.url);
  if (request.nextUrl.pathname !== "/") {
    login.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
  }
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except /login and the health check, which the container's own
  // healthcheck hits unauthenticated.
  //
  // "/api/agent" is listed exactly, without ":path*": /api/agent/skill is the
  // sidecar's HMAC-signed callback and arrives with no cookie by design, so
  // sweeping the subtree in here would 401 the fallback path permanently.
  matcher: [
    "/",
    "/overview/:path*",
    "/stores/:path*",
    "/products/:path*",
    "/associates/:path*",
    "/actions/:path*",
    "/trust/:path*",
    "/api/agent",
  ],
};
