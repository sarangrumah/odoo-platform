// =============================================================================
// Authentication.
//
// Credentials are checked by Odoo itself (`/web/session/authenticate` against
// prd_levis_begbal) — this app never sees a password hash and has no user table
// of its own. On success we mint our own short-lived signed cookie and throw
// Odoo's session away: the dashboard reads Postgres directly, so it has no use
// for an Odoo session beyond the moment of proving who you are.
//
// It must be `odoo-front`: the public `odoo` runs dbfilter ^%d$ and answers
// "Database not found" for this tenant, exactly as it does for the login
// gateway.
// =============================================================================

import { createHmac, timingSafeEqual, randomUUID } from "node:crypto";
import { cookies } from "next/headers";

const COOKIE = "finance_session";
const ODOO_URL = (process.env.FINANCE_ODOO_URL ?? "http://odoo-front:8069").replace(/\/+$/, "");
const DB = process.env.FINANCE_DB_NAME ?? "prd_levis_begbal";
const TTL_SECONDS = Number(process.env.FINANCE_SESSION_TTL ?? 60 * 60 * 12);

export interface Session {
  uid: number;
  login: string;
  name: string;
  exp: number;
}

function secret(): string {
  const value = process.env.FINANCE_SESSION_SECRET;
  // Fail closed. A default secret would mean anyone who read this file could
  // forge a session cookie.
  if (!value || value.length < 32) {
    throw new Error("FINANCE_SESSION_SECRET is missing or shorter than 32 characters");
  }
  return value;
}

function sign(payload: string): string {
  return createHmac("sha256", secret()).update(payload).digest("base64url");
}

function encode(session: Session): string {
  const payload = Buffer.from(JSON.stringify(session)).toString("base64url");
  return `${payload}.${sign(payload)}`;
}

function decode(token: string): Session | null {
  const [payload, signature] = token.split(".");
  if (!payload || !signature) return null;

  const expected = Buffer.from(sign(payload));
  const actual = Buffer.from(signature);
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) return null;

  try {
    const session = JSON.parse(Buffer.from(payload, "base64url").toString()) as Session;
    if (typeof session.exp !== "number" || session.exp * 1000 < Date.now()) return null;
    return session;
  } catch {
    return null;
  }
}

// --- Brute-force throttle ----------------------------------------------------
// In-memory is enough: there is one container, and the point is to make an
// online guessing attack impractical, not to survive a restart.

const failures = new Map<string, { count: number; until: number }>();
const MAX_FAILURES = 5;
const LOCKOUT_MS = 5 * 60_000;

function throttleKey(login: string): string {
  return login.trim().toLowerCase();
}

export function lockedOut(login: string): number {
  const entry = failures.get(throttleKey(login));
  if (!entry || entry.until < Date.now()) return 0;
  return entry.count >= MAX_FAILURES ? Math.ceil((entry.until - Date.now()) / 1000) : 0;
}

function noteFailure(login: string) {
  const key = throttleKey(login);
  const entry = failures.get(key);
  const count = entry && entry.until > Date.now() ? entry.count + 1 : 1;
  failures.set(key, { count, until: Date.now() + LOCKOUT_MS });
}

function clearFailures(login: string) {
  failures.delete(throttleKey(login));
}

// --- Odoo round trip ---------------------------------------------------------

interface AuthResult {
  ok: boolean;
  session?: Session;
  error?: string;
}

export async function authenticate(login: string, password: string): Promise<AuthResult> {
  const wait = lockedOut(login);
  if (wait) {
    return { ok: false, error: `Terlalu banyak percobaan gagal. Coba lagi dalam ${wait} detik.` };
  }

  let response: Response;
  try {
    response = await fetch(`${ODOO_URL}/web/session/authenticate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        method: "call",
        id: randomUUID(),
        params: { db: DB, login, password },
      }),
      signal: AbortSignal.timeout(15_000),
      cache: "no-store",
    });
  } catch (error) {
    console.error("[auth] Odoo unreachable", error);
    return { ok: false, error: "Server autentikasi tidak dapat dihubungi." };
  }

  const body = (await response.json().catch(() => null)) as {
    result?: { uid?: number | false; name?: string; username?: string; is_admin?: boolean };
    error?: { data?: { name?: string } };
  } | null;

  const uid = body?.result?.uid;
  if (!body || !uid) {
    noteFailure(login);
    // Odoo answers AccessDenied for both a wrong password and an unknown user;
    // say the same thing back either way rather than confirming which logins
    // exist.
    return { ok: false, error: "Login atau kata sandi salah." };
  }

  // Portal and public users authenticate happily but have no business reading
  // company-wide revenue, so the check is on `share`, not on any group.
  const internal = await isInternalUser(response, uid);
  if (!internal) {
    noteFailure(login);
    return { ok: false, error: "Akun ini tidak punya akses ke dasbor." };
  }

  clearFailures(login);
  return {
    ok: true,
    session: {
      uid,
      login: body.result?.username ?? login,
      name: body.result?.name ?? login,
      exp: Math.floor(Date.now() / 1000) + TTL_SECONDS,
    },
  };
}

/** Reads res.users.share with the freshly minted Odoo session cookie. */
async function isInternalUser(authResponse: Response, uid: number): Promise<boolean> {
  const cookie = authResponse.headers.get("set-cookie");
  if (!cookie) return false;

  try {
    const result = await fetch(`${ODOO_URL}/web/dataset/call_kw`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Cookie: cookie.split(";")[0] },
      body: JSON.stringify({
        jsonrpc: "2.0",
        method: "call",
        id: randomUUID(),
        params: {
          model: "res.users",
          method: "read",
          args: [[uid], ["share", "active"]],
          kwargs: {},
        },
      }),
      signal: AbortSignal.timeout(15_000),
      cache: "no-store",
    });
    const body = (await result.json()) as { result?: { share?: boolean; active?: boolean }[] };
    const record = body.result?.[0];
    // Fail closed: an unreadable answer is not a pass.
    return record?.share === false && record?.active === true;
  } catch (error) {
    console.error("[auth] could not verify user type", error);
    return false;
  }
}

// --- Cookie ------------------------------------------------------------------

export async function storeSession(session: Session) {
  const jar = await cookies();
  jar.set(COOKIE, encode(session), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: TTL_SECONDS,
  });
}

export async function clearSession() {
  (await cookies()).delete(COOKIE);
}

export async function getSession(): Promise<Session | null> {
  const token = (await cookies()).get(COOKIE)?.value;
  return token ? decode(token) : null;
}

export const SESSION_COOKIE = COOKIE;
