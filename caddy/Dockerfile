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
# Everything is PINNED and the CRS tarball is checksum-verified: this binary
# terminates TLS for production, so a compromised or moved upstream tag must not
# be able to change what gets built. Bump deliberately, never with `latest`, and
# re-scan afterwards:
#
#   docker build -f caddy/Dockerfile -t odoo19-platform-caddy-waf:<ver> caddy/
#   trivy image --severity HIGH,CRITICAL --ignore-unfixed \
#     odoo19-platform-caddy-waf:<ver>
#
# CI's container-scan matrix includes this image, so a bump that reintroduces a
# HIGH fails the PR instead of reaching the front door.
# ============================================================

# ---- Build -------------------------------------------------------------------
# golang:1.26-alpine rather than Caddy's own builder image: the toolchain version
# is itself a scan finding, so it has to be something this file controls. The tag
# floats within 1.26.x deliberately -- a stdlib CVE is fixed by rebuilding, not by
# editing this file, and eight of them (CVE-2026-33818, -39821, -46600, -56853,
# -56858, -56859, -56860, -56862) were cleared by nothing more than a --no-cache
# rebuild picking up 1.26.8 over 1.26.5.
FROM golang:1.26-alpine AS builder

# hadolint DL4006: nothing in this stage pipes today, but SHELL applies to the
# whole stage and a future RUN with a pipe must not swallow a failing left side.
SHELL ["/bin/ash", "-o", "pipefail", "-c"]

# git is what Go uses to fetch the two plugin repositories.
# hadolint ignore=DL3018
RUN apk add --no-cache git ca-certificates

ARG CADDY_VERSION=2.11.4
ARG CORAZA_VERSION=v2.5.0
ARG RATELIMIT_VERSION=v0.1.0

WORKDIR /build
COPY main.go ./main.go

# Three groups, in order: Caddy itself, the two plugins, and transitive modules
# raised ABOVE what Caddy's go.mod asks for.
#
# That third group is the whole reason this build is a plain `go build` over an
# explicit go.mod rather than `xcaddy build`. The first version of this image used
# xcaddy and trivy immediately found 20 HIGH/CRITICAL CVEs in it — Caddy 2.11.3
# itself (2, fixed in 2.11.4), x/crypto (9), x/net (3), x/text, grpc, go-jose and
# the Go stdlib. xcaddy resolves whatever the pinned Caddy requires and offers no
# lever to raise a transitive module.
#
# Remove an entry from the third group only after confirming upstream's go.mod has
# caught up, otherwise the CVE returns silently.
#
# The versions in that group are higher than the ones trivy names as the fix,
# because the modules constrain each other and `go get` refuses a lower pin
# outright rather than resolving upward. Raise as a set, not one at a time: the
# 4-Sep-2026 bump for CVE-2026-56854 needed three rounds of `docker build` to
# find the closure -- x/crypto@v0.55.0 demands x/net@v0.57.0, and the two of
# them together demand x/text@v0.41.0.
#
# NOTE: no `#` comments inside the RUN below. The backslashes join it into one
# logical shell line, so a `#` at the start of a continued line begins a comment
# that swallows every remaining argument — the build would succeed with half the
# pins silently dropped.
RUN go mod init eal-hub/caddy \
 && go get "github.com/caddyserver/caddy/v2@v${CADDY_VERSION}" \
 && go get "github.com/corazawaf/coraza-caddy/v2@${CORAZA_VERSION}" \
 && go get "github.com/mholt/caddy-ratelimit@${RATELIMIT_VERSION}" \
 && go get \
      golang.org/x/crypto@v0.55.0 \
      golang.org/x/net@v0.57.0 \
      golang.org/x/text@v0.41.0 \
      google.golang.org/grpc@v1.83.1 \
      github.com/go-jose/go-jose/v3@v3.0.5 \
 && go mod tidy \
 && CGO_ENABLED=0 go build -trimpath -ldflags "-w -s" -o /out/caddy .

# ---- Core Rule Set -----------------------------------------------------------
FROM alpine:3.22 AS crs

ARG CRS_VERSION=4.28.0
ARG CRS_SHA256=d8acc96f25ad07c8e3a595a23c797324f6d77e59ddf9e26e90dd95ebd2e676ce

# hadolint DL4006: the checksum verification below pipes into sha256sum, and a
# failing left-hand side must fail the build rather than be swallowed.
SHELL ["/bin/ash", "-o", "pipefail", "-c"]

# hadolint ignore=DL3018
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
FROM caddy:2.11.4-alpine

# Same reason as the CRS stage: the module check at the end pipes into grep, and a
# caddy binary that fails to run must fail the build.
SHELL ["/bin/ash", "-o", "pipefail", "-c"]

# The base image lags Alpine's package repo by however long since its release;
# libssl3, libcrypto3, c-ares and curl were all HIGH findings on an untouched
# base. This is the one place a floating version is the safer choice.
# hadolint ignore=DL3018
RUN apk upgrade --no-cache

COPY --from=builder /out/caddy /usr/bin/caddy
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
# binary would leave the Caddyfile referencing directives that do not exist, and
# Caddy would crash-loop with ingress down rather than merely unprotected.
RUN caddy list-modules | grep -q '^http.handlers.waf$' \
 && caddy list-modules | grep -q '^http.handlers.rate_limit$'
