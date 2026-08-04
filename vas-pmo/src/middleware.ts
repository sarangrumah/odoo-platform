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

  const login = new URL("/login", request.url);
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
