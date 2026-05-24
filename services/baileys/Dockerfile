# syntax=docker/dockerfile:1.7
# Baileys WhatsApp sidecar service for custom_whatsapp module.

FROM node:20-alpine AS deps
WORKDIR /app
# Baileys pulls some sub-dependencies directly from git; npm needs `git`
# available during `install` to resolve them.
RUN apk add --no-cache git
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund --loglevel=error \
 && npm cache clean --force

FROM node:20-alpine AS runtime
ENV NODE_ENV=production \
    PORT=8088 \
    BAILEYS_AUTH_DIR=/var/lib/baileys
WORKDIR /app
RUN addgroup -g 10104 -S baileys \
 && adduser -u 10104 -G baileys -S baileys \
 && mkdir -p /var/lib/baileys \
 && chown -R baileys:baileys /var/lib/baileys
COPY package.json ./
COPY --from=deps /app/node_modules ./node_modules
COPY src ./src
USER baileys
EXPOSE 8088
VOLUME ["/var/lib/baileys"]
HEALTHCHECK --interval=20s --timeout=5s --retries=5 --start-period=10s \
  CMD wget -qO- http://localhost:8088/healthz >/dev/null 2>&1 || exit 1
CMD ["node", "src/server.js"]
