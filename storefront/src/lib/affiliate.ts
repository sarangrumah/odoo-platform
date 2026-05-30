"use client";

/**
 * Affiliate attribution helpers (spec F6). The first-party `aff_ref` cookie is
 * consent-gated (skipped when the visitor rejected cookies) and lives for the
 * attribution window. Odoo enforces validity/anti-fraud server-side.
 */

const AFF_COOKIE = "aff_ref";
const SESSION_KEY = "gw-aff-session";
const CONSENT_KEY = "gw-cookie-consent";
const WINDOW_DAYS = 30;

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

export function getAffiliateCode(): string | null {
  return readCookie(AFF_COOKIE);
}

function consentAllowed(): boolean {
  // Privacy-preserving: only skip when the visitor explicitly rejected.
  return typeof localStorage !== "undefined" && localStorage.getItem(CONSENT_KEY) !== "rejected";
}

function getSession(): string {
  let s = localStorage.getItem(SESSION_KEY);
  if (!s) {
    s = Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(SESSION_KEY, s);
  }
  return s;
}

/** Called on page load: if `?aff=CODE` is present, capture + ping Odoo. */
export async function captureAffiliate() {
  if (typeof window === "undefined") return;
  const code = new URLSearchParams(window.location.search).get("aff");
  if (!code) return;
  if (!consentAllowed()) return;

  const maxAge = WINDOW_DAYS * 24 * 60 * 60;
  document.cookie = `${AFF_COOKIE}=${encodeURIComponent(code)}; path=/; max-age=${maxAge}; SameSite=Lax`;

  try {
    const qs = new URLSearchParams({
      code,
      landing: window.location.pathname,
      ref: document.referrer || "",
      session: getSession(),
    });
    await fetch(`/api/affiliate/track?${qs.toString()}`, { cache: "no-store" });
  } catch {
    /* tracking is best-effort */
  }
}
