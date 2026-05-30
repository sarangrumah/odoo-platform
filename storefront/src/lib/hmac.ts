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
