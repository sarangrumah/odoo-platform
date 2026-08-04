# Gentle Woman storefront — Next.js (standalone) multi-stage build.
#   1. builder: install deps + next build → .next/standalone
#   2. runtime: trim to standalone server, run as non-root.
# Mirrors the hub-portal hardening pattern (non-root, healthcheck, read-only fs).

FROM node:20-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund --loglevel=error
COPY . .
RUN npm run build

FROM node:20-alpine AS runtime
# HOSTNAME=0.0.0.0 so the Next standalone server binds all interfaces — Docker
# otherwise sets HOSTNAME to the container id and the localhost healthcheck fails.
ENV NODE_ENV=production \
    PORT=8080 \
    HOSTNAME=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
RUN addgroup -g 10105 -S shop && adduser -u 10105 -G shop -S shop
# The Next standalone server is started directly with `node`; npm and corepack
# are never invoked at runtime. They ship with node:20-alpine anyway, and npm's
# own dependency tree (tar, minimatch, glob, brace-expansion, ...) accounts for
# 18 HIGH/CRITICAL trivy findings unreachable from application code. Drop them.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
           /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
 && apk upgrade --no-cache libssl3 libcrypto3
# Standalone output bundles only the needed node_modules + server.js.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
USER shop
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=5s --retries=5 --start-period=20s \
  CMD ["/bin/sh", "-c", "wget -qO- http://127.0.0.1:8080/api/health >/dev/null 2>&1 || exit 1"]
CMD ["node", "server.js"]
