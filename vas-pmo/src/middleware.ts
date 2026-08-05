import { NextResponse, type NextRequest } from "next/server";

/**
 * Gate every app route on the presence of a session cookie.
 *
 * Presence only — validity is checked server-side on each request. The middleware's job is
 * to keep anonymous traffic off the app shell, not to be the security boundary.
 */
export function middleware(request: NextRequest) {
  const hasSession =
    request.cookies.has("vaspmo_at") || request.cookies.has("vaspmo_rt");
  if (hasSession) return NextResponse.next();

  // The basePath has to be written in by hand. `nextUrl.pathname` comes with it already
  // stripped, and `NextResponse.redirect` takes an absolute URL, so neither end puts it
  // back: an anonymous hit on /vaspmo/board would be sent to /login, which the shared
  // Caddy hands to Odoo instead of to this app. `next` stays prefix-free on purpose --
  // the post-login `redirect()` is basePath-aware and would double it.
  const login = new URL(`${request.nextUrl.basePath}/login`, request.url);
  login.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: [
    "/portfolio/:path*",
    "/board/:path*",
    "/tasks/:path*",
    "/weekly/:path*",
    "/cr/:path*",
    "/timeline/:path*",
    "/logs/:path*",
    "/settings/:path*",
  ],
};
