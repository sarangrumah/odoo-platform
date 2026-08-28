// =============================================================================
// The escalation path: hand the sentence to the Claude Code sidecar.
//
// The sidecar cannot reach Postgres. It calls back into /api/agent/skill to run
// the very same skills the deterministic path runs, so there is exactly one
// process holding the `cockpit_ro` credentials and exactly one definition of
// what is answerable. This module is only the transport.
// =============================================================================

import { createHmac, timingSafeEqual } from "node:crypto";

import type { Answer } from "@/lib/agent/answer";
import type { Extent, Filters } from "@/lib/filters";

const TIMEOUT_MS = 60_000;

/**
 * Sign like ai-gateway/app/security.py does: HMAC-SHA256 over "<ts>.<body>",
 * carried in one header. Reusing the platform's existing scheme means the
 * sidecar's verifier is a straight port, not a new invention.
 */
export function sign(secret: string, rawBody: string): Record<string, string> {
  const ts = Math.floor(Date.now() / 1000).toString();
  const mac = createHmac("sha256", secret);
  mac.update(`${ts}.${rawBody}`, "utf8");
  return { "X-Custom-Signature": `t=${ts},v1=${mac.digest("hex")}` };
}

/** Constant-time compare of two hex digests. */
export function verify(secret: string, rawBody: string, header: string | null): boolean {
  if (!header) return false;
  const m = header.match(/^t=(\d+),v1=([0-9a-f]{64})$/);
  if (!m) return false;
  const ts = Number(m[1]);
  if (!Number.isFinite(ts) || Math.abs(Date.now() / 1000 - ts) > 300) return false;

  const expected = createHmac("sha256", secret).update(`${ts}.${rawBody}`, "utf8").digest();
  const given = Buffer.from(m[2], "hex");
  if (given.length !== expected.length) return false;
  return timingSafeEqual(expected, given);
}

export function fallbackConfigured(): boolean {
  return Boolean(process.env.COCKPIT_AGENT_URL && process.env.COCKPIT_AGENT_SECRET);
}

export interface FallbackRequest {
  question: string;
  filters: Filters;
  extent: Extent;
}

export async function askFallback(req: FallbackRequest): Promise<Answer | null> {
  const url = process.env.COCKPIT_AGENT_URL;
  const secret = process.env.COCKPIT_AGENT_SECRET;
  if (!url || !secret) return null;

  const body = JSON.stringify(req);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(`${url}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...sign(secret, body) },
      body,
      signal: controller.signal,
    });
    if (!res.ok) {
      console.warn("[agent] sidecar returned", res.status);
      return null;
    }
    const data = (await res.json()) as Partial<Answer>;
    if (typeof data.headline !== "string" || !data.headline.trim()) return null;

    return {
      source: "claude",
      headline: data.headline,
      table: data.table,
      href: data.href,
      note: data.note,
      skill: data.skill,
    };
  } catch (err) {
    // A sidecar that is down, slow, or misconfigured must never take the
    // assistant with it — the catalogue answered everything up to this point.
    console.warn("[agent] sidecar unreachable:", (err as Error).message);
    return null;
  } finally {
    clearTimeout(timer);
  }
}
