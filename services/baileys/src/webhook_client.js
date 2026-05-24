import crypto from 'node:crypto';
import { logger } from './logger.js';

const ODOO_WEBHOOK_BASE = (process.env.ODOO_WEBHOOK_BASE || '').replace(/\/+$/, '');

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
