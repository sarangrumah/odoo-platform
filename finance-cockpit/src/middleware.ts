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
  if (request.cookies.has("finance_session")) return NextResponse.next();

  // basePath has to be written back in by hand: `nextUrl.pathname` arrives with
  // it stripped and `NextResponse.redirect` wants an absolute URL, so without
  // this an anonymous hit on /finance/ap would be sent to /login — which the
  // shared Caddy hands to Odoo, not to this app.
  const login = new URL(`${request.nextUrl.basePath}/login`, request.url);
  if (request.nextUrl.pathname !== "/") {
    login.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
  }
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except /login and the health check, which the container's own
  // healthcheck hits unauthenticated.
  matcher: ["/", "/ap/:path*", "/pos/:path*", "/openitems/:path*", "/close/:path*", "/tie/:path*"],
};
