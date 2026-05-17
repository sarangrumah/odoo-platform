// HMAC-SHA256 signer matching app.security in ai-gateway / tenant-orchestrator.
// Format: t=<unix_ts>,v1=<hex>
//   HMAC over: f"{ts}.{raw_body}"

import crypto from 'k6/crypto';

export function signCustom(secret, body) {
  const ts = Math.floor(Date.now() / 1000);
  const payload = `${ts}.${body || ''}`;
  const sig = crypto.hmac('sha256', secret, payload, 'hex');
  return { header: `t=${ts},v1=${sig}`, ts };
}
