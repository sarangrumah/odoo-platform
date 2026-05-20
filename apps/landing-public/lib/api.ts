/**
 * Server-side HMAC signing helper for orchestrator calls.
 *
 * Mirrors logic from addons/verticals/custom_super_admin/models/orchestrator_client.py
 * Signature scheme (parity with tenant-orchestrator/app/security.py):
 *   header: X-Custom-Signature: t=<unix_ts>,v1=<hex(hmac_sha256(secret, f"{ts}.{body}"))>
 *   actor : X-Custom-Actor:     landing-public
 *
 * This module MUST be called only from server contexts (Route Handlers,
 * Server Components, Server Actions). The shared secret is never exposed
 * to the browser.
 */

import { createHmac } from 'node:crypto';

const DEFAULT_BASE = 'http://orchestrator:8000';
const DEFAULT_TIMEOUT_MS = 60_000;

function getBaseUrl(): string {
  return (process.env.ORCHESTRATOR_BASE_URL || DEFAULT_BASE).replace(/\/+$/, '');
}

function getSecret(): string {
  const secret = process.env.ORCHESTRATOR_SHARED_SECRET;
  if (!secret || secret.length < 32) {
    throw new Error(
      'ORCHESTRATOR_SHARED_SECRET missing or too short (>=32 chars required)',
    );
  }
  return secret;
}

function sign(bodyBytes: Buffer): { signature: string; ts: string } {
  const ts = Math.floor(Date.now() / 1000).toString();
  const msg = Buffer.concat([Buffer.from(ts, 'utf8'), Buffer.from('.', 'utf8'), bodyBytes]);
  const hex = createHmac('sha256', getSecret()).update(msg).digest('hex');
  return { signature: `t=${ts},v1=${hex}`, ts };
}

export interface OrchestratorCallOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  path: string;
  body?: unknown;
  actor?: string;
  timeoutMs?: number;
}

export async function callOrchestrator<T = unknown>({
  method = 'GET',
  path,
  body,
  actor = 'landing-public',
  timeoutMs = DEFAULT_TIMEOUT_MS,
}: OrchestratorCallOptions): Promise<T> {
  const url = `${getBaseUrl()}${path.startsWith('/') ? path : `/${path}`}`;
  const bodyBytes =
    body === undefined || body === null ? Buffer.alloc(0) : Buffer.from(JSON.stringify(body), 'utf8');
  const { signature } = sign(bodyBytes);

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);

  try {
    const resp = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-Custom-Signature': signature,
        'X-Custom-Actor': actor,
      },
      body: bodyBytes.length ? bodyBytes : undefined,
      signal: ctrl.signal,
      cache: 'no-store',
    });

    const text = await resp.text();
    if (!resp.ok) {
      throw new Error(
        `Orchestrator ${method} ${path} -> ${resp.status}: ${text.slice(0, 300)}`,
      );
    }
    if (resp.status === 204 || !text) return {} as T;
    return JSON.parse(text) as T;
  } finally {
    clearTimeout(timer);
  }
}
