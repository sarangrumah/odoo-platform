# syntax=docker/dockerfile:1.7
# Erajaya Odoo Hub portal — multi-stage build.
#   1. builder: install deps, build Vite SPA into /app/dist
#   2. runtime: trim down to runtime deps + dist, run Express BFF.

FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund --no-package-lock --loglevel=error
COPY vite.config.js index.html tsconfig.json ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM node:20-alpine AS runtime
ENV NODE_ENV=production \
    PORT=8080
WORKDIR /app
RUN addgroup -g 10103 -S portal && adduser -u 10103 -G portal -S portal
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund --no-package-lock --loglevel=error \
 && npm cache clean --force
COPY server ./server
COPY --from=builder /app/dist ./dist
USER portal
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=5s --retries=5 --start-period=10s \
  CMD wget -qO- http://localhost:8080/healthz >/dev/null 2>&1 || exit 1
CMD ["node", "server/index.mjs"]
