import { Router } from 'express';
import {
  startSession,
  getSession,
  logoutSession,
  listSessions,
} from '../session_manager.js';

export const sessionsRouter = Router();

sessionsRouter.get('/', (_req, res) => {
  res.json({ sessions: listSessions() });
});

sessionsRouter.post('/:sessionId/start', async (req, res) => {
  const { sessionId } = req.params;
  const accountId = Number(req.body?.account_id || req.query.account_id);
  const hmacSecret = req.body?.hmac_secret || req.query.hmac_secret || '';
  try {
    const out = await startSession({ sessionId, accountId, hmacSecret });
    res.json({ session_id: sessionId, ...out });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

sessionsRouter.get('/:sessionId/status', (req, res) => {
  const rec = getSession(req.params.sessionId);
  if (!rec) return res.status(404).json({ error: 'unknown session' });
  res.json({
    session_id: rec.sessionId,
    status: rec.status,
    phone: rec.phone,
    has_qr: !!rec.qrPng,
    last_error: rec.lastError,
  });
});

sessionsRouter.get('/:sessionId/qr', (req, res) => {
  const rec = getSession(req.params.sessionId);
  if (!rec) return res.status(404).json({ error: 'unknown session' });
  if (!rec.qrPng) return res.status(404).json({ error: 'no qr available', status: rec.status });
  if (req.query.format === 'base64') {
    return res.json({ session_id: rec.sessionId, png_base64: rec.qrPng.toString('base64') });
  }
  res.setHeader('Content-Type', 'image/png');
  res.setHeader('Cache-Control', 'no-store');
  res.end(rec.qrPng);
});

sessionsRouter.post('/:sessionId/logout', async (req, res) => {
  try {
    const out = await logoutSession(req.params.sessionId);
    res.json(out);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});
