// =============================================================================
// Session handling.
//
// Tokens live in httpOnly cookies, never in localStorage: an XSS on the board must not
// be able to walk away with a token that can write to Odoo.
// =============================================================================

import { cookies } from "next/headers";

import { odooFetch } from "./odoo";

const ACCESS_COOKIE = "vaspmo_at";
const REFRESH_COOKIE = "vaspmo_rt";

export interface SessionUser {
  id: number;
  login: string;
  name: string;
  email: string;
  roles: string[];
  verticals: Array<{ id: number; code: string; name: string }>;
}

const cookieOptions = {
  httpOnly: true as const,
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production",
  path: "/",
};

export async function storeSession(access: string, refresh: string, expiresIn: number) {
  const jar = await cookies();
  jar.set(ACCESS_COOKIE, access, { ...cookieOptions, maxAge: expiresIn });
  jar.set(REFRESH_COOKIE, refresh, { ...cookieOptions, maxAge: 60 * 60 * 24 * 14 });
}

export async function clearSession() {
  const jar = await cookies();
  jar.delete(ACCESS_COOKIE);
  jar.delete(REFRESH_COOKIE);
}

export async function getAccessToken(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(ACCESS_COOKIE)?.value ?? null;
}

/**
 * Access token, refreshed transparently when it has expired.
 * Returns null when the caller has to log in again.
 */
export async function getValidToken(): Promise<string | null> {
  const jar = await cookies();
  const access = jar.get(ACCESS_COOKIE)?.value;
  if (access) return access;

  const refresh = jar.get(REFRESH_COOKIE)?.value;
  if (!refresh) return null;

  const result = await odooFetch<{ access: string; refresh: string; expires_in: number }>(
    "/vaspmo/api/auth/refresh",
    { method: "POST", body: { refresh } },
  );
  if (!result.ok || !result.data) {
    await clearSession();
    return null;
  }
  await storeSession(result.data.access, result.data.refresh, result.data.expires_in);
  return result.data.access;
}

export async function getSessionUser(): Promise<SessionUser | null> {
  const token = await getValidToken();
  if (!token) return null;
  const result = await odooFetch<SessionUser>("/vaspmo/api/auth/me", { token });
  return result.ok ? result.data : null;
}

/** GET helper for server components. */
export async function api<T>(path: string): Promise<T | null> {
  const token = await getValidToken();
  if (!token) return null;
  const result = await odooFetch<T>(path, { token });
  return result.data;
}
