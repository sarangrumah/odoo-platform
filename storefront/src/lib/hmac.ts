import { createHmac } from "node:crypto";

/**
 * Sign a request body for Odoo's custom_core `@secure_endpoint` decorator.
 *
 * Canonical form (see addons/core/custom_core/controllers/secure_endpoint.py
 * `_verify_hmac`): HMAC-SHA256(secret, ascii(timestamp) + raw_body) → hex.
 * Headers: X-Signature, X-Timestamp. Server-side only — never ship the
 * secret to the browser.
 */
export function signSecureEndpoint(
  secret: string,
  rawBody: string,
): { "X-Signature": string; "X-Timestamp": string } {
  const ts = Math.floor(Date.now() / 1000).toString();
  const mac = createHmac("sha256", secret);
  mac.update(ts, "ascii");
  mac.update(rawBody, "utf8");
  return { "X-Signature": mac.digest("hex"), "X-Timestamp": ts };
}

/**
 * Sign a request for the AI gateway's HMACMiddleware (ai-gateway/app/security.py).
 *
 * Canonical form differs from Odoo's: HMAC-SHA256(secret, "<ts>.<raw_body>")
 * (a literal "." joins the timestamp and body), emitted as a single header
 * `X-Custom-Signature: t=<unix_ts>,v1=<hex>`. Server-side only.
 */
export function signGateway(secret: string, rawBody: string): { "X-Custom-Signature": string } {
  const ts = Math.floor(Date.now() / 1000).toString();
  const mac = createHmac("sha256", secret);
  mac.update(`${ts}.${rawBody}`, "utf8");
  return { "X-Custom-Signature": `t=${ts},v1=${mac.digest("hex")}` };
}
