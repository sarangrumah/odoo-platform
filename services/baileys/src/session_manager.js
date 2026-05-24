import path from 'node:path';
import fs from 'node:fs/promises';
import qrcode from 'qrcode';
import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import { logger, childLogger } from './logger.js';
import { postEvent } from './webhook_client.js';

const AUTH_ROOT = process.env.BAILEYS_AUTH_DIR || '/var/lib/baileys';

const sessions = new Map();

function makeSessionRecord(sessionId, accountId, hmacSecret) {
  return {
    sessionId,
    accountId,
    hmacSecret,
    sock: null,
    status: 'starting',
    qrPng: null,
    phone: null,
    startedAt: Date.now(),
    lastError: null,
  };
}

async function loadAuth(sessionId) {
  const dir = path.join(AUTH_ROOT, sessionId);
  await fs.mkdir(dir, { recursive: true });
  return useMultiFileAuthState(dir);
}

async function wipeAuth(sessionId) {
  const dir = path.join(AUTH_ROOT, sessionId);
  await fs.rm(dir, { recursive: true, force: true });
}

export function getSession(sessionId) {
  return sessions.get(sessionId);
}

export function listSessions() {
  return Array.from(sessions.values()).map((s) => ({
    sessionId: s.sessionId,
    accountId: s.accountId,
    status: s.status,
    phone: s.phone,
    startedAt: s.startedAt,
  }));
}

export async function startSession({ sessionId, accountId, hmacSecret }) {
  if (!sessionId) throw new Error('sessionId is required');

  const existing = sessions.get(sessionId);
  if (existing && existing.status === 'connected') {
    return { status: existing.status, phone: existing.phone };
  }

  const log = childLogger({ sessionId, accountId });
  const record =
    existing || makeSessionRecord(sessionId, accountId, hmacSecret);
  record.accountId = accountId || record.accountId;
  record.hmacSecret = hmacSecret || record.hmacSecret;
  sessions.set(sessionId, record);

  const { state, saveCreds } = await loadAuth(sessionId);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket.default
    ? makeWASocket.default({ auth: state, version, printQRInTerminal: false, logger: pinoSilent(log) })
    : makeWASocket({ auth: state, version, printQRInTerminal: false, logger: pinoSilent(log) });

  record.sock = sock;
  record.status = state.creds?.registered ? 'connecting' : 'qr_pending';

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      record.status = 'qr_pending';
      try {
        record.qrPng = await qrcode.toBuffer(qr, { type: 'png', margin: 1, width: 320 });
      } catch (err) {
        log.error({ err: err.message }, 'failed to render QR PNG');
      }
    }
    if (connection === 'open') {
      record.status = 'connected';
      record.qrPng = null;
      record.phone = sock.user?.id?.split(':')[0] || null;
      record.lastError = null;
      log.info({ phone: record.phone }, 'session connected');
      void postEvent({
        accountId: record.accountId,
        eventType: 'connection',
        hmacSecret: record.hmacSecret,
        payload: { session_id: sessionId, status: 'connected', phone: record.phone },
      });
    }
    if (connection === 'close') {
      const statusCode = new Boom(lastDisconnect?.error)?.output?.statusCode;
      const loggedOut = statusCode === DisconnectReason.loggedOut;
      record.status = loggedOut ? 'disconnected' : 'error';
      record.lastError = lastDisconnect?.error?.message || String(statusCode);
      log.warn({ statusCode, loggedOut, err: record.lastError }, 'session closed');
      void postEvent({
        accountId: record.accountId,
        eventType: 'connection',
        hmacSecret: record.hmacSecret,
        payload: {
          session_id: sessionId,
          status: record.status,
          error: record.lastError,
          logged_out: loggedOut,
        },
      });
      if (!loggedOut) {
        // Reconnect after a short delay; persisted creds make this seamless.
        setTimeout(() => {
          void startSession({ sessionId, accountId: record.accountId, hmacSecret: record.hmacSecret });
        }, 5000);
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ messages }) => {
    for (const msg of messages || []) {
      if (msg.key?.fromMe) continue;
      if (!msg.message) continue;
      const from = msg.key.remoteJid || '';
      const phoneOnly = from.split('@')[0] || '';
      const text =
        msg.message.conversation ||
        msg.message.extendedTextMessage?.text ||
        '';
      const type =
        msg.message.conversation || msg.message.extendedTextMessage
          ? 'text'
          : msg.message.imageMessage
          ? 'image'
          : msg.message.documentMessage
          ? 'document'
          : 'unknown';
      void postEvent({
        accountId: record.accountId,
        eventType: 'message',
        hmacSecret: record.hmacSecret,
        payload: {
          session_id: sessionId,
          message: {
            id: msg.key.id,
            from: phoneOnly,
            type,
            text,
            timestamp: msg.messageTimestamp,
          },
        },
      });
    }
  });

  sock.ev.on('messages.update', async (updates) => {
    for (const u of updates || []) {
      const status = u.update?.status;
      if (!status) continue;
      // Baileys status enum: 1=PENDING, 2=SERVER_ACK, 3=DELIVERY_ACK, 4=READ, 5=PLAYED, 0=ERROR
      const statusMap = { 1: 'sent', 2: 'sent', 3: 'delivered', 4: 'read', 0: 'failed' };
      void postEvent({
        accountId: record.accountId,
        eventType: 'status',
        hmacSecret: record.hmacSecret,
        payload: {
          session_id: sessionId,
          id: u.key?.id,
          status: statusMap[status] || 'unknown',
          remote_jid: u.key?.remoteJid,
        },
      });
    }
  });

  return { status: record.status, phone: record.phone };
}

export async function logoutSession(sessionId) {
  const record = sessions.get(sessionId);
  if (record?.sock) {
    try {
      await record.sock.logout();
    } catch (err) {
      logger.warn({ sessionId, err: err.message }, 'logout error (continuing)');
    }
  }
  sessions.delete(sessionId);
  await wipeAuth(sessionId);
  return { ok: true };
}

export async function sendMessage(sessionId, { to, type, text, mediaUrl, caption, filename }) {
  const record = sessions.get(sessionId);
  if (!record || !record.sock) {
    throw Object.assign(new Error('session not started'), { httpStatus: 409 });
  }
  if (record.status !== 'connected') {
    throw Object.assign(new Error(`session not connected (status=${record.status})`), { httpStatus: 409 });
  }
  const jid = normalizeJid(to);
  let result;
  if (type === 'image' && mediaUrl) {
    result = await record.sock.sendMessage(jid, { image: { url: mediaUrl }, caption: caption || '' });
  } else if (type === 'document' && mediaUrl) {
    result = await record.sock.sendMessage(jid, {
      document: { url: mediaUrl },
      mimetype: 'application/pdf',
      fileName: filename || 'document.pdf',
      caption: caption || '',
    });
  } else {
    result = await record.sock.sendMessage(jid, { text: text || '' });
  }
  return { id: result?.key?.id || null };
}

function normalizeJid(input) {
  if (!input) throw new Error('to is required');
  if (input.includes('@')) return input;
  const digits = String(input).replace(/[^0-9]/g, '');
  if (!digits) throw new Error('to contains no digits');
  return `${digits}@s.whatsapp.net`;
}

// Baileys expects a pino-compatible logger. We give it one at warn level so
// it doesn't flood our logs with internal protocol chatter.
function pinoSilent(parent) {
  return parent.child({ component: 'baileys' }, { level: 'warn' });
}
