import pino from 'pino';

const level = process.env.LOG_LEVEL || 'info';

export const logger = pino({
  level,
  base: { service: 'baileys-sidecar' },
  timestamp: pino.stdTimeFunctions.isoTime,
});

export function childLogger(bindings) {
  return logger.child(bindings);
}
