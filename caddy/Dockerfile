# ============================================================
# Caddy for the front door, with a WAF and a rate limiter compiled in.
#
# The stock caddy:2-alpine image has neither, and both are Go modules that can
# only enter Caddy at build time — hence this image. It replaces caddy:2-alpine
# in docker-compose.multitenant.yml and changes nothing else about how Caddy
# runs: same Caddyfile, same volumes, same ports.
#
#   coraza-caddy   ModSecurity-compatible WAF (SecLang), so the OWASP Core Rule
#                  Set runs at the edge — SQL injection, XSS, RCE, traversal,
#                  scanner fingerprints. This is the same engine the (inert)
#                  nginx/modsecurity/ stub was written for, moved to the hop
#                  that actually serves eal-hub.erajaya.com.
#   caddy-ratelimit  per-client-IP request ceilings, which is what turns
#                  /web/login and /web/session/authenticate from an unlimited
#                  credential-stuffing target into a throttled one.
#
# Versions are PINNED, and the CRS tarball is checksum-verified: this binary
# terminates TLS for production, so a compromised or moved upstream tag must not
# be able to change what gets built. Bump deliberately, never with `latest`.
# ============================================================

ARG CADDY_VERSION=2.11.3

FROM caddy:${CADDY_VERSION}-builder-alpine AS builder

RUN xcaddy build \
    --with github.com/corazawaf/coraza-caddy/v2@v2.5.0 \
    --with github.com/mholt/caddy-ratelimit@v0.1.0

# ---- Core Rule Set -----------------------------------------------------------
FROM alpine:3.22 AS crs

ARG CRS_VERSION=4.28.0
ARG CRS_SHA256=d8acc96f25ad07c8e3a595a23c797324f6d77e59ddf9e26e90dd95ebd2e676ce

RUN apk add --no-cache curl tar
WORKDIR /tmp
RUN curl -fsSLO "https://github.com/coreruleset/coreruleset/archive/refs/tags/v${CRS_VERSION}.tar.gz" \
 && echo "${CRS_SHA256}  v${CRS_VERSION}.tar.gz" | sha256sum -c - \
 && mkdir -p /crs \
 && tar -xzf "v${CRS_VERSION}.tar.gz" -C /crs --strip-components=1 \
 # crs-setup.conf.example is the file CRS expects to be copied and edited. It is
 # used as shipped; our deviations from it live in caddy/coraza/crs-tuning.conf,
 # which is included after it so a CRS bump cannot silently drop them.
 && cp /crs/crs-setup.conf.example /crs/crs-setup.conf \
 && rm -rf /tmp/*.tar.gz /crs/tests /crs/util /crs/docs /crs/.github

# ---- Runtime -----------------------------------------------------------------
FROM caddy:${CADDY_VERSION}-alpine

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
# CRS lives OUTSIDE /etc/caddy/coraza on purpose: that directory is a read-only
# bind mount of caddy/coraza/ from the repo (engine config, CRS tuning,
# exclusions), and mounting it over a path that also held the rule set would hide
# the rules and leave the WAF with nothing to enforce.
COPY --from=crs /crs /etc/coraza/coreruleset

# Audit log destination. Coraza writes one entry per rule match here; the
# container runs as root (Caddy needs NET_BIND_SERVICE on 80/443) so no chown is
# needed, but the directory has to exist or the engine refuses to start.
RUN mkdir -p /var/log/coraza

# Fail the build if either module is missing — a silent fallback to a stock
# binary would leave the Caddyfile referencing directives that do not exist,
# and Caddy would crash-loop with ingress down rather than merely unprotected.
RUN caddy list-modules | grep -q '^http.handlers.waf$' \
 && caddy list-modules | grep -q '^http.handlers.rate_limit$'
