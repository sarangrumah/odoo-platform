import { Router } from 'express';
import { sendMessage } from '../session_manager.js';

export const messagesRouter = Router();

messagesRouter.post('/:sessionId/messages', async (req, res) => {
  const { sessionId } = req.params;
  const { to, type, text, media_url, caption, filename } = req.body || {};
  if (!to) return res.status(400).json({ error: 'to is required' });
  try {
    const result = await sendMessage(sessionId, {
      to,
      type: type || 'text',
      text,
      mediaUrl: media_url,
      caption,
      filename,
    });
    res.json({ session_id: sessionId, ...result });
  } catch (err) {
    const status = err.httpStatus || 500;
    res.status(status).json({ error: err.message });
  }
});
