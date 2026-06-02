import { readFileSync } from "node:fs";
import { Agent } from "undici";
import { signSecureEndpoint } from "./hmac";

/**
 * Server-side Odoo client used exclusively by the BFF route handlers.
 *
 * The browser never imports this module — the Odoo origin, the HMAC secret
 * and the customer JWT all stay on the server. Tenant resolution relies on
 * Odoo's dbfilter (^%d$) so we set the Host header to the tenant subdomain.
 */

const ODOO_BASE_URL = process.env.ODOO_BASE_URL || "http://odoo:8069";

/**
 * When ODOO_BASE_URL is https (BFF→Odoo over the internal nginx TLS terminator),
 * pin the internal self-signed cert: trust ONLY that cert (`ca`) and skip the
 * hostname check (the cert's CN is `localhost`, not `nginx`). This encrypts the
 * one internal hop that previously carried the JWT + PII in cleartext, without
 * weakening TLS verification globally or touching the shared cert.
 */
let odooDispatcher: Agent | undefined;
if (ODOO_BASE_URL.startsWith("https")) {
  try {
    const ca = readFileSync(process.env.ODOO_INTERNAL_CA || "/etc/ssl/odoo-internal.crt");
    odooDispatcher = new Agent({
      connect: { ca, checkServerIdentity: () => undefined },
    });
  } catch (e) {
    // No CA mounted → fall back to the platform trust store (will fail TLS if
    // the cert is untrusted, surfacing a clear error rather than silent http).
    console.error("odoo internal CA not loaded:", String(e));
  }
}

/** Merge the pinned-TLS dispatcher into a fetch init (undici extension). */
function withTls(init: RequestInit): RequestInit {
  return odooDispatcher ? ({ ...init, dispatcher: odooDispatcher } as RequestInit) : init;
}
const ODOO_TENANT_DB = process.env.ODOO_TENANT_DB || "gentle_woman";
const ODOO_TENANT_HOST =
  process.env.ODOO_TENANT_HOST || `${ODOO_TENANT_DB}.platform.localhost`;
const HMAC_SECRET = process.env.STOREFRONT_HMAC_SECRET || "";

function tenantHeaders(): Record<string, string> {
  // X-Odoo-Database selects the tenant DB directly (Odoo 19) — reliable
  // because Node's fetch strips the Host header. X-Tenant-Slug matches the
  // platform's nginx/Caddy auditing convention.
  return {
    "X-Odoo-Database": ODOO_TENANT_DB,
    "X-Tenant-Slug": ODOO_TENANT_DB,
  };
}

export interface ProxyInit {
  method?: string;
  /** Forward the customer's Authorization: Bearer header verbatim. */
  authorization?: string | null;
  /** Raw request body (already a string). */
  body?: string | null;
  /** Extra query string (without leading ?). */
  query?: string;
}

/** Proxy to a public/JWT storefront endpoint: /storefront/api/<path>. */
export async function odooFetch(path: string, init: ProxyInit = {}): Promise<Response> {
  const qs = init.query ? `?${init.query}` : "";
  const url = `${ODOO_BASE_URL}/storefront/api/${path}${qs}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...tenantHeaders(),
  };
  if (init.authorization) headers.Authorization = init.authorization;

  return fetch(url, withTls({
    method: init.method || "GET",
    headers,
    body: init.body ?? undefined,
    cache: "no-store",
  }));
}

/** Server-to-server admin call, HMAC-signed: /storefront/api/admin/<path>. */
export async function odooAdminFetch(path: string, payload: unknown = {}): Promise<Response> {
  if (!HMAC_SECRET) {
    throw new Error("STOREFRONT_HMAC_SECRET is not configured");
  }
  const rawBody = JSON.stringify(payload ?? {});
  const sig = signSecureEndpoint(HMAC_SECRET, rawBody);
  const url = `${ODOO_BASE_URL}/storefront/api/admin/${path}`;
  return fetch(url, withTls({
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...tenantHeaders(),
      ...sig,
    },
    body: rawBody,
    cache: "no-store",
  }));
}

/** Fetch an arbitrary Odoo path (e.g. /web/image/...) with tenant resolution. */
export async function odooRawFetch(path: string, query = ""): Promise<Response> {
  const clean = path.replace(/^\/+/, "");
  const qs = query ? (query.startsWith("?") ? query : `?${query}`) : "";
  return fetch(`${ODOO_BASE_URL}/${clean}${qs}`, withTls({
    headers: { ...tenantHeaders() },
    cache: "no-store",
  }));
}

export const PUBLIC_ODOO_URL = process.env.NEXT_PUBLIC_ODOO_PUBLIC_URL || "";

/** Server-side product fetch for SEO/OG metadata (generateMetadata). */
export async function getProductServer(
  id: string,
  lang = "id",
): Promise<{ id: number; name: string; summary?: string } | null> {
  try {
    const res = await odooFetch(`products/${id}`, { query: `lang=${lang}` });
    if (!res.ok) return null;
    const json = await res.json();
    return json?.ok ? json.data : null;
  } catch {
    return null;
  }
}
