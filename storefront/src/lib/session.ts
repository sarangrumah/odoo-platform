import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { odooFetch } from "./odoo";
import { rateLimit, policyFor } from "./ratelimit";

/**
 * Server-only session helpers. Auth tokens live in HttpOnly cookies set by the
 * BFF — never in JS-readable storage — so an XSS can't exfiltrate them. The
 * browser only ever holds the non-sensitive `customer` object.
 *
 * Defense-in-depth: the token is additionally SEALED with AES-256-GCM before it
 * goes into the cookie, so the signed JWT (and its email claim) is unreadable at
 * rest on the user's disk. Odoo still receives a normal HS256 JWT (the proxy
 * un-seals it server-side) — no Odoo/auth_jwt change.
 */
export const AT = "gw_at"; // access token (short-lived)
export const RT = "gw_rt"; // refresh token (long-lived)

const COOKIE = {
  httpOnly: true,
  secure: true,
  sameSite: "lax" as const,
  path: "/",
};

// 32-byte AES key derived from a dedicated secret (falls back to the HMAC secret
// so no new env is mandatory). Rotating it invalidates live cookie sessions.
const COOKIE_KEY = createHash("sha256")
  .update(process.env.STOREFRONT_COOKIE_KEY || process.env.STOREFRONT_HMAC_SECRET || "gw-dev-cookie-key")
  .digest();

/** AES-256-GCM seal → base64url(iv|tag|ciphertext). */
export function sealToken(plain: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", COOKIE_KEY, iv, { authTagLength: 16 });
  const ct = Buffer.concat([cipher.update(plain, "utf8"), cipher.final()]);
  return Buffer.concat([iv, cipher.getAuthTag(), ct]).toString("base64url");
}

/** Reverse of sealToken; returns null on any tamper/format/key error (fail closed). */
export function openToken(sealed: string | undefined): string | null {
  if (!sealed) return null;
  try {
    const buf = Buffer.from(sealed, "base64url");
    const iv = buf.subarray(0, 12);
    const tag = buf.subarray(12, 28);
    const ct = buf.subarray(28);
    const decipher = createDecipheriv("aes-256-gcm", COOKIE_KEY, iv, { authTagLength: 16 });
    decipher.setAuthTag(tag);
    return Buffer.concat([decipher.update(ct), decipher.final()]).toString("utf8");
  } catch {
    return null;
  }
}

export function setAuthCookies(
  res: NextResponse,
  tokens: { access?: string; refresh?: string },
) {
  if (tokens.access) res.cookies.set(AT, sealToken(tokens.access), { ...COOKIE, maxAge: 900 });
  if (tokens.refresh) {
    res.cookies.set(RT, sealToken(tokens.refresh), { ...COOKIE, maxAge: 60 * 60 * 24 * 30 });
  }
}

export function clearAuthCookies(res: NextResponse) {
  res.cookies.set(AT, "", { ...COOKIE, maxAge: 0 });
  res.cookies.set(RT, "", { ...COOKIE, maxAge: 0 });
}

function clientIp(req: NextRequest): string {
  return (req.headers.get("x-forwarded-for") || "").split(",")[0].trim() || "unknown";
}

/**
 * Forward an auth call to Odoo, then move the returned tokens into HttpOnly
 * cookies and hand the browser only `{customer, is_guest}`.
 */
export async function authProxy(req: NextRequest, odooPath: string): Promise<NextResponse> {
  const policy = policyFor(odooPath);
  if (policy && !rateLimit(`${clientIp(req)}:${odooPath}`, policy.limit, policy.windowMs)) {
    return NextResponse.json(
      { ok: false, error_code: "RATE_LIMITED", message: "Too many requests." },
      { status: 429, headers: { "Retry-After": "60" } },
    );
  }

  const body = await req.text();
  if (body.length > 64 * 1024) {
    return NextResponse.json(
      { ok: false, error_code: "PAYLOAD_TOO_LARGE", message: "Request body too large." },
      { status: 413 },
    );
  }

  let upstream: Response;
  try {
    upstream = await odooFetch(odooPath, { method: "POST", body });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error_code: "UPSTREAM_UNREACHABLE", message: String(e) },
      { status: 502 },
    );
  }
  const json = await upstream.json().catch(() => ({ ok: false }));
  if (!upstream.ok || !json.ok) {
    return NextResponse.json(json, { status: upstream.status || 400 });
  }
  const { access, refresh, customer, is_guest } = json.data;
  const res = NextResponse.json({ ok: true, data: { customer, is_guest: !!is_guest } });
  setAuthCookies(res, { access, refresh });
  return res;
}
