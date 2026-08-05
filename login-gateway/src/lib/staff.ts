import { timingSafeEqual } from "node:crypto";

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
