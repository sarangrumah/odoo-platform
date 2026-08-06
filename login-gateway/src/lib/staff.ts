import { createHmac, timingSafeEqual } from "node:crypto";

/**
 * The staff unlock.
 *
 * Internal environments (working copies, R&D, demo builds) are absent from the
 * chooser by default. Opening `/signin?staff=<key>` once drops a cookie that
 * adds them back for this browser; the middleware strips the key from the URL
 * immediately so it does not sit in history, in a bookmark, or in a Referer.
 *
 * This is a convenience gate on a LISTING, not an authorisation boundary — the
 * real one is still Odoo asking for a password on the next page. It exists so a
 * client never reads our internal database inventory, not to keep a determined
 * attacker away from a login form.
 */

export const STAFF_COOKIE = "lg_staff";

/** 12 hours: long enough for a working day, short enough that a shared laptop forgets. */
export const STAFF_COOKIE_MAX_AGE = 12 * 60 * 60;

/** Unset key = the unlock is disabled and internal entries stay hidden for everyone. */
export function staffKey(): string | null {
  const key = process.env.STAFF_KEY?.trim();
  return key ? key : null;
}

/** Constant-time compare, with the length check kept out of the timing path. */
export function isValidStaffKey(candidate: string | undefined | null): boolean {
  const expected = staffKey();
  if (!expected || !candidate) return false;

  const a = Buffer.from(candidate, "utf8");
  const b = Buffer.from(expected, "utf8");
  // timingSafeEqual throws on length mismatch, so pad to a common length and
  // fold the real length comparison into the result instead of returning early.
  const len = Math.max(a.length, b.length);
  const pa = Buffer.alloc(len);
  const pb = Buffer.alloc(len);
  a.copy(pa);
  b.copy(pb);
  return timingSafeEqual(pa, pb) && a.length === b.length;
}

/**
 * The cookie has to be unforgeable too, not just the key that mints it.
 *
 * It used to hold the literal "1", so the whole gate was "type lg_staff=1 into
 * devtools". Measured against the live site on 6-Aug-2026: a request carrying
 * that header got the staff view of /versi -- 354 KB with every commit subject
 * and hash, against 132 KB for an anonymous one -- and would equally have
 * unlocked the internal environments in the chooser. A cookie the visitor can
 * write is not a gate.
 *
 * The value is now `<expiry>.<HMAC-SHA256(expiry, STAFF_KEY)>`. The expiry sits
 * inside the signed payload, so it cannot be extended by editing the cookie and
 * the browser's maxAge is only a courtesy. Rotating STAFF_KEY invalidates every
 * outstanding cookie, which is what you want from a rotation.
 *
 * Still a gate on a LISTING, not an authorisation boundary -- Odoo asking for a
 * password on the next page remains the real one.
 */
function signStaff(exp: number, key: string): string {
  return createHmac("sha256", key).update(String(exp)).digest("base64url");
}

/** Cookie value for a fresh unlock, or null when the unlock is disabled. */
export function mintStaffCookie(nowMs: number = Date.now()): string | null {
  const key = staffKey();
  if (!key) return null;
  const exp = Math.floor(nowMs / 1000) + STAFF_COOKIE_MAX_AGE;
  return `${exp}.${signStaff(exp, key)}`;
}

/** True only for a cookie this server minted, and that has not expired. */
export function isStaffCookieValid(value: string | undefined | null, nowMs: number = Date.now()): boolean {
  const key = staffKey();
  if (!key || !value) return false;

  const dot = value.indexOf(".");
  if (dot <= 0) return false;

  const exp = Number(value.slice(0, dot));
  if (!Number.isSafeInteger(exp) || exp * 1000 <= nowMs) return false;

  const expected = Buffer.from(signStaff(exp, key), "utf8");
  const got = Buffer.from(value.slice(dot + 1), "utf8");
  // A genuine MAC has a fixed length, so returning early here leaks nothing an
  // attacker does not already know from the format.
  if (expected.length !== got.length) return false;
  return timingSafeEqual(expected, got);
}
