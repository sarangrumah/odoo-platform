import { logger } from './logger.js';

const SHARED_SECRET = process.env.BAILEYS_SHARED_SECRET || '';

export function requireBearer(req, res, next) {
  if (!SHARED_SECRET) {
    logger.error('BAILEYS_SHARED_SECRET is not set — refusing all requests');
    return res.status(503).json({ error: 'service not configured' });
  }
  const header = req.headers.authorization || '';
  const expected = `Bearer ${SHARED_SECRET}`;
  if (header.length !== expected.length) {
    return res.status(401).json({ error: 'unauthorized' });
  }
  let diff = 0;
  for (let i = 0; i < expected.length; i++) {
    diff |= header.charCodeAt(i) ^ expected.charCodeAt(i);
  }
  if (diff !== 0) {
    return res.status(401).json({ error: 'unauthorized' });
  }
  return next();
}
