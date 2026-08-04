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
# The runtime never shells out to npm — the BFF is started directly with `node`.
# But node:20-alpine bundles npm and corepack, and npm's own dependency tree
# (tar, minimatch, glob, brace-expansion, cross-spawn, sigstore, ip-address)
# accounts for 18 HIGH/CRITICAL trivy findings that no application change can
# ever fix. Delete them in the same layer as the install, so they never land in
# the image at all. openssl is patched separately (CVE-2026-45447).
RUN npm install --omit=dev --no-audit --no-fund --no-package-lock --loglevel=error \
 && npm cache clean --force \
 && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
           /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack
RUN apk upgrade --no-cache libssl3 libcrypto3
COPY server ./server
COPY --from=builder /app/dist ./dist
USER portal
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=5s --retries=5 --start-period=10s \
  CMD ["/bin/sh", "-c", "wget -qO- http://localhost:8080/healthz >/dev/null 2>&1 || exit 1"]
CMD ["node", "server/index.mjs"]
