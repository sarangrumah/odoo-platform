/**
 * Tiny in-memory fixed-window rate limiter for the BFF (single-instance).
 * For multi-instance deployments back this with Redis; here it throttles
 * brute-force / abuse against sensitive auth + signup endpoints.
 */
type Bucket = { count: number; reset: number };
const buckets = new Map<string, Bucket>();

export function rateLimit(key: string, limit: number, windowMs: number): boolean {
  const now = Date.now();
  const b = buckets.get(key);
  if (!b || now > b.reset) {
    buckets.set(key, { count: 1, reset: now + windowMs });
    if (buckets.size > 5000) {
      for (const [k, v] of buckets) if (now > v.reset) buckets.delete(k);
    }
    return true;
  }
  if (b.count >= limit) return false;
  b.count += 1;
  return true;
}

/** Per-path rate-limit policy (requests per 60s window). */
export function policyFor(path: string): { limit: number; windowMs: number } | null {
  if (/^auth\/(login|register|guest)$/.test(path)) return { limit: 8, windowMs: 60_000 };
  if (path === "newsletter") return { limit: 5, windowMs: 60_000 };
  if (/^auth\/refresh$/.test(path)) return { limit: 30, windowMs: 60_000 };
  return null;
}
