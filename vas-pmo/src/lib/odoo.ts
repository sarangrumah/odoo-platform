// =============================================================================
// BFF -> Odoo client.
//
// Mirrors storefront/src/lib/odoo.ts: the hop rides TLS with the internal CA pinned, so
// the JWT never crosses the docker network in clear text.
// =============================================================================

import { readFileSync } from "node:fs";
import { Agent } from "node:https";

const ODOO_BASE_URL = (process.env.ODOO_BASE_URL ?? "http://odoo:8069").replace(/\/+$/, "");
const ODOO_TENANT_DB = process.env.ODOO_TENANT_DB ?? "rnd_vas_pmo";
const ODOO_TENANT_HOST = process.env.ODOO_TENANT_HOST ?? "";
const ODOO_INTERNAL_CA = process.env.ODOO_INTERNAL_CA ?? "";

let agent: Agent | undefined;
if (ODOO_BASE_URL.startsWith("https://") && ODOO_INTERNAL_CA) {
  try {
    agent = new Agent({ ca: readFileSync(ODOO_INTERNAL_CA), keepAlive: true });
  } catch (error) {
    console.error("[Odoo] Could not read ODOO_INTERNAL_CA, falling back to system trust", error);
  }
}

export interface OdooResult<T> {
  ok: boolean;
  status: number;
  data: T | null;
  error?: { code: string; message: string };
}

export async function odooFetch<T = unknown>(
  path: string,
  options: {
    method?: "GET" | "POST" | "PATCH";
    token?: string;
    body?: unknown;
    hmac?: { timestamp: string; signature: string };
    timeoutMs?: number;
    cache?: RequestCache;
  } = {},
): Promise<OdooResult<T>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  if (ODOO_TENANT_HOST) headers.Host = ODOO_TENANT_HOST;
  if (options.hmac) {
    headers["X-Timestamp"] = options.hmac.timestamp;
    headers["X-Signature"] = options.hmac.signature;
  }

  const url = `${ODOO_BASE_URL}${path}${path.includes("?") ? "&" : "?"}db=${encodeURIComponent(ODOO_TENANT_DB)}`;
  const init: RequestInit & { dispatcher?: unknown } = {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: AbortSignal.timeout(options.timeoutMs ?? 20_000),
    cache: options.cache ?? "no-store",
  };
  // Node's fetch honours a custom agent through this non-standard field.
  if (agent) (init as { agent?: Agent }).agent = agent;

  try {
    const response = await fetch(url, init as RequestInit);
    const text = await response.text();
    let parsed: { ok?: boolean; data?: T; error?: { code: string; message: string } } = {};
    try {
      parsed = text ? JSON.parse(text) : {};
    } catch {
      return {
        ok: false,
        status: response.status,
        data: null,
        error: { code: "BAD_JSON", message: text.slice(0, 200) },
      };
    }
    return {
      ok: response.ok && parsed.ok !== false,
      status: response.status,
      data: (parsed.data ?? null) as T | null,
      error: parsed.error,
    };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`[Odoo] ${path} failed: ${message}`);
    return { ok: false, status: 0, data: null, error: { code: "NETWORK", message } };
  }
}
