import express from 'express';
import { logger } from './logger.js';
import { requireBearer } from './auth.js';
import { sessionsRouter } from './routes/sessions.js';
import { messagesRouter } from './routes/messages.js';

const PORT = Number(process.env.PORT || 8088);

const app = express();
app.use(express.json({ limit: '2mb' }));

app.get('/healthz', (_req, res) => res.json({ ok: true }));

app.use('/sessions', requireBearer, sessionsRouter);
app.use('/sessions', requireBearer, messagesRouter);

app.use((err, _req, res, _next) => {
  logger.error({ err: err.message, stack: err.stack }, 'unhandled error');
  res.status(500).json({ error: 'internal error' });
});

app.listen(PORT, () => {
  logger.info({ port: PORT }, 'baileys sidecar listening');
});
