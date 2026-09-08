// =============================================================================
// Fixed-window rate limiting, in memory.
//
// Ported from storefront/src/lib/ratelimit.ts. The cockpit runs as a single
// container, so a shared store would be ceremony; if it is ever scaled out this
// needs to move to Redis, and the limits below become per-instance until it does.
// =============================================================================

type Bucket = { count: number; reset: number };

const buckets = new Map<string, Bucket>();

export function rateLimit(key: string, limit: number, windowMs: number): boolean {
  const now = Date.now();
  const b = buckets.get(key);
  if (!b || now > b.reset) {
    buckets.set(key, { count: 1, reset: now + windowMs });
    // Sweep on insert rather than on a timer: the map only grows when new keys
    // arrive, so that is exactly when it is worth paying for a cleanup.
    if (buckets.size > 5000) {
      for (const [k, v] of buckets) if (now > v.reset) buckets.delete(k);
    }
    return true;
  }
  if (b.count >= limit) return false;
  b.count += 1;
  return true;
}

const inFlight = new Set<string>();

/**
 * At most one concurrent run per key.
 *
 * The fallback path holds a model call open for tens of seconds; without this a
 * reader who taps send five times would queue five inferences and pay for all
 * of them. Returns null when a run is already in flight.
 */
export async function once<T>(key: string, fn: () => Promise<T>): Promise<T | null> {
  if (inFlight.has(key)) return null;
  inFlight.add(key);
  try {
    return await fn();
  } finally {
    inFlight.delete(key);
  }
}
