# syntax=docker/dockerfile:1
# Multi-stage, standalone output, non-root, read-only-friendly.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev || npm install --omit=dev

FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=8080
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
# Read at runtime rather than bundled, so a tenant can be added by editing the
# file (or bind-mounting over it) without rebuilding the image.
COPY --from=builder --chown=nextjs:nodejs /app/config ./config
USER nextjs
EXPOSE 8080
CMD ["node", "server.js"]
