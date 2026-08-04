import crypto from 'node:crypto';
import { logger } from './logger.js';

const ODOO_WEBHOOK_BASE = (process.env.ODOO_WEBHOOK_BASE || '').replace(/\/+$/, '');

// Which tenant database the events belong to.
//
// Required whenever Odoo serves more than one database: with `dbfilter = ^.*$`
// an unauthenticated POST carries nothing Odoo can resolve a database from, so
// every event dies as `404 No database is selected and the requested URL was
// not found in the server-wide controllers` -- a message that reads like a
// missing route and sends you hunting for a controller that is in fact present
// and installed. `?db=` is NOT honoured in Odoo 19; the supported mechanism is
// this header, which Odoo names in an HTML comment inside that very 404 page.
const ODOO_WEBHOOK_DB = (process.env.ODOO_WEBHOOK_DB || '').trim();

let warnedNoDb = false;

function signBody(secret, bodyString) {
  return 'sha256=' + crypto.createHmac('sha256', secret).update(bodyString).digest('hex');
}

export async function postEvent({ accountId, eventType, hmacSecret, payload }) {
  if (!ODOO_WEBHOOK_BASE) {
    logger.warn({ accountId, eventType }, 'ODOO_WEBHOOK_BASE not set — dropping event');
    return { ok: false, dropped: true };
  }
  if (!accountId) {
    logger.warn({ eventType }, 'missing accountId for event — dropping');
    return { ok: false, dropped: true };
  }
  const url = `${ODOO_WEBHOOK_BASE}/custom_whatsapp/webhook/${accountId}`;
  const body = JSON.stringify(payload || {});
  const signature = hmacSecret ? signBody(hmacSecret, body) : '';
  const headers = {
    'Content-Type': 'application/json',
    'X-Baileys-Event': eventType,
  };
  if (signature) {
    headers['X-Baileys-Signature'] = signature;
  }
  if (ODOO_WEBHOOK_DB) {
    headers['X-Odoo-Database'] = ODOO_WEBHOOK_DB;
  } else if (!warnedNoDb) {
    // Say this once, loudly. Left unset, every event below is guaranteed to
    // 404 on a multi-database Odoo, and the 404 blames the URL rather than the
    // missing header.
    warnedNoDb = true;
    logger.warn(
      { hint: 'set ODOO_WEBHOOK_DB (compose: BAILEYS_ODOO_WEBHOOK_DB) to the tenant database that owns whatsapp.account' },
      'ODOO_WEBHOOK_DB not set — events will 404 unless Odoo serves exactly one database',
    );
  }
  try {
    const resp = await fetch(url, { method: 'POST', headers, body });
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      logger.warn({ accountId, eventType, status: resp.status, text: text.slice(0, 200) }, 'webhook non-2xx');
      return { ok: false, status: resp.status };
    }
    return { ok: true, status: resp.status };
  } catch (err) {
    logger.error({ accountId, eventType, err: err.message }, 'webhook POST failed');
    return { ok: false, error: err.message };
  }
}
