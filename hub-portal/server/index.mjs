// hub-portal Express proxy.
//
// Responsibilities:
//   * HMAC-sign outbound calls to tenant-orchestrator (/v1/*) using the
//     scheme defined in tenant-orchestrator/app/security.py:
//       X-Custom-Signature: t=<unix_ts>,v1=<hex(hmac_sha256(secret, f"{ts}.{body}"))>
//       X-Custom-Actor:     hub-portal
//   * Bridge Odoo JSON-RPC calls (cookie-based session).
//   * Surface narrow proxy routes for VPS / intake / backups so the browser
//     never touches the shared secret.
//
// Env vars:
//   ORCHESTRATOR_BASE_URL       (default: http://orchestrator:8000)
//   ORCHESTRATOR_SHARED_SECRET  (>= 32 chars, required for HMAC calls)
//   ODOO_BASE_URL               (default: http://odoo:8069)
//   ODOO_DB / ODOO_LOGIN / ODOO_PASSWORD  (for JSON-RPC bridge)
//   PORT                        (default: 18001)

import express from 'express';
import { createHmac } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DIST_DIR = path.resolve(__dirname, '..', 'dist');

const ORCH_BASE = (process.env.ORCHESTRATOR_BASE_URL || 'http://orchestrator:8000').replace(/\/+$/, '');
const ORCH_SECRET = process.env.ORCHESTRATOR_SHARED_SECRET || '';
const ODOO_BASE = (process.env.ODOO_BASE_URL || 'http://odoo:8069').replace(/\/+$/, '');
const ODOO_DB = process.env.ODOO_DB || '';
const ODOO_LOGIN = process.env.ODOO_LOGIN || '';
const ODOO_PASSWORD = process.env.ODOO_PASSWORD || '';
const PORT = Number(process.env.PORT || 18001);
const ACTOR = 'hub-portal';

function signBody(bodyBytes) {
  if (!ORCH_SECRET || ORCH_SECRET.length < 32) {
    throw new Error('ORCHESTRATOR_SHARED_SECRET missing or too short (>=32 chars)');
  }
  const ts = Math.floor(Date.now() / 1000).toString();
  const msg = Buffer.concat([Buffer.from(ts, 'utf8'), Buffer.from('.', 'utf8'), bodyBytes]);
  const hex = createHmac('sha256', ORCH_SECRET).update(msg).digest('hex');
  return `t=${ts},v1=${hex}`;
}

async function callOrch(method, path, body) {
  const url = `${ORCH_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  const bodyBytes = body == null ? Buffer.alloc(0) : Buffer.from(JSON.stringify(body), 'utf8');
  const sig = signBody(bodyBytes);
  const resp = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Custom-Signature': sig,
      'X-Custom-Actor': ACTOR,
    },
    body: bodyBytes.length ? bodyBytes : undefined,
  });
  const text = await resp.text();
  return { status: resp.status, body: text };
}

const app = express();
app.use(express.json({ limit: '20mb' }));

app.get('/health', (_req, res) => res.json({ ok: true, service: 'hub-portal-proxy' }));

// ---------------------------------------------------------------------------
// Intake (orchestrator passthrough)
// ---------------------------------------------------------------------------
app.post('/api/intake/submit', async (req, res) => {
  try {
    const r = await callOrch('POST', '/v1/intake/submit', req.body);
    res.status(r.status).type('application/json').send(r.body);
  } catch (e) {
    res.status(500).json({ detail: String(e?.message || e) });
  }
});

app.get('/api/intake/status/:token', async (req, res) => {
  try {
    const r = await callOrch('GET', `/v1/intake/${encodeURIComponent(req.params.token)}/status`);
    res.status(r.status).type('application/json').send(r.body);
  } catch (e) {
    res.status(500).json({ detail: String(e?.message || e) });
  }
});

// ---------------------------------------------------------------------------
// VPS (orchestrator passthrough)
// ---------------------------------------------------------------------------
app.get('/api/vps', async (_req, res) => {
  // VPS inventory lives in Odoo (tenant.vps); orchestrator only handles lifecycle.
  try {
    const r = await odooCall('tenant.vps', 'search_read', [[]], {
      fields: ['id', 'name', 'public_ip', 'state', 'provider', 'region',
               'cpu_cores', 'ram_mb', 'disk_gb', 'last_health_check_at',
               'prometheus_target_url', 'grafana_dashboard_uid'],
      limit: 500,
      order: 'name',
    });
    const text = await r.text();
    let parsed;
    try { parsed = JSON.parse(text); } catch { return res.status(r.status).type('application/json').send(text); }
    if (parsed?.error) return res.status(500).json({ detail: parsed.error?.data?.message || 'Odoo error', error: parsed.error });
    res.status(r.status).json(parsed.result ?? []);
  } catch (e) {
    res.status(500).json({ detail: String(e?.message || e) });
  }
});

app.get('/api/vps/:id', async (req, res) => {
  try {
    const r = await odooCall('tenant.vps', 'read', [[Number(req.params.id)]], {});
    const text = await r.text();
    let parsed;
    try { parsed = JSON.parse(text); } catch { return res.status(r.status).type('application/json').send(text); }
    if (parsed?.error) return res.status(500).json({ detail: parsed.error?.data?.message || 'Odoo error', error: parsed.error });
    const recs = parsed.result || [];
    res.status(r.status).json(recs[0] || null);
  } catch (e) {
    res.status(500).json({ detail: String(e?.message || e) });
  }
});

app.post('/api/vps/register', async (req, res) => {
  try {
    const r = await callOrch('POST', '/v1/vps/register', req.body);
    res.status(r.status).type('application/json').send(r.body);
  } catch (e) {
    res.status(500).json({ detail: String(e?.message || e) });
  }
});

app.post('/api/vps/:id/bootstrap', async (req, res) => {
  try {
    const r = await callOrch('POST', `/v1/vps/${req.params.id}/bootstrap`, {});
    res.status(r.status).type('application/json').send(r.body);
  } catch (e) {
    res.status(500).json({ detail: String(e?.message || e) });
  }
});

app.post('/api/vps/:id/deploy', async (req, res) => {
  try {
    const r = await callOrch('POST', `/v1/vps/${req.params.id}/deploy`, req.body || {});
    res.status(r.status).type('application/json').send(r.body);
  } catch (e) {
    res.status(500).json({ detail: String(e?.message || e) });
  }
});

// ---------------------------------------------------------------------------
// Backups
// ---------------------------------------------------------------------------
app.post('/api/backups/:id/replicate', async (req, res) => {
  try {
    const r = await callOrch('POST', `/v1/backups/${req.params.id}/replicate`, req.body || {});
    res.status(r.status).type('application/json').send(r.body);
  } catch (e) {
    res.status(500).json({ detail: String(e?.message || e) });
  }
});

// ---------------------------------------------------------------------------
// Odoo JSON-RPC bridge
//
// Session is cached in-memory; for prod, persist per-user. The browser POSTs
// { model, method, args, kwargs } and we translate to Odoo's RPC envelope.
// ---------------------------------------------------------------------------
let odooSessionCookie = null;

async function odooAuthenticate() {
  if (!ODOO_DB || !ODOO_LOGIN) throw new Error('ODOO_DB / ODOO_LOGIN not configured');
  const resp = await fetch(`${ODOO_BASE}/web/session/authenticate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0',
      params: { db: ODOO_DB, login: ODOO_LOGIN, password: ODOO_PASSWORD },
    }),
  });
  if (!resp.ok) throw new Error(`Odoo auth -> ${resp.status}`);
  const setCookie = resp.headers.get('set-cookie');
  if (setCookie) odooSessionCookie = setCookie.split(';')[0];
  return resp.json();
}

async function odooCall(model, method, args, kwargs) {
  if (!odooSessionCookie) await odooAuthenticate();
  const payload = {
    jsonrpc: '2.0',
    method: 'call',
    params: { model, method, args: args || [], kwargs: kwargs || {} },
  };
  const doFetch = () =>
    fetch(`${ODOO_BASE}/web/dataset/call_kw`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Cookie: odooSessionCookie || '',
      },
      body: JSON.stringify(payload),
    });

  let resp = await doFetch();
  if (resp.status === 401 || resp.status === 403) {
    odooSessionCookie = null;
    await odooAuthenticate();
    resp = await doFetch();
  }
  return resp;
}

app.post('/api/odoo/jsonrpc', async (req, res) => {
  const { model, method, args, kwargs } = req.body || {};
  if (!model || !method) {
    return res.status(400).json({ detail: 'model + method required' });
  }
  try {
    const r = await odooCall(model, method, args, kwargs);
    const text = await r.text();
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      return res.status(r.status).type('application/json').send(text);
    }
    if (parsed?.error) {
      return res.status(500).json({ detail: parsed.error?.data?.message || 'Odoo RPC error', error: parsed.error });
    }
    return res.status(r.status).json(parsed.result ?? {});
  } catch (e) {
    return res.status(500).json({ detail: String(e?.message || e) });
  }
});

// ---------------------------------------------------------------------------
// Auth stubs (browser hits these from Login.tsx).
// Wire to real SSO / Odoo session as Track I matures.
// ---------------------------------------------------------------------------
app.post('/api/auth/login', (req, res) => {
  const { email, password } = req.body || {};
  if (!email || !password) return res.status(400).json({ detail: 'missing creds' });
  // TODO: forward to Odoo /web/session/authenticate or external IdP
  return res.json({ ok: true, email });
});
app.post('/api/auth/logout', (_req, res) => res.json({ ok: true }));
app.get('/api/auth/me', (_req, res) => res.json({ email: ODOO_LOGIN || 'unknown' }));

// ---------------------------------------------------------------------------
// Static SPA + healthcheck. All non-/api routes fall through to index.html.
// ---------------------------------------------------------------------------
app.get('/healthz', (_req, res) => res.json({ ok: true }));
app.use(express.static(DIST_DIR, { index: false, maxAge: '1h' }));
app.get(/^(?!\/api\/).*/, (_req, res) => res.sendFile(path.join(DIST_DIR, 'index.html')));

app.listen(PORT, () => {
  // eslint-disable-next-line no-console
  console.log(`[hub-portal] proxy listening on :${PORT} -> orchestrator=${ORCH_BASE} odoo=${ODOO_BASE}`);
});
