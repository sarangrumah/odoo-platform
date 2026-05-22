#!/usr/bin/env bash
# ============================================================
# Odoo healthcheck — just verify the HTTP worker is responding.
# We don't probe DB-aware endpoints (/web/login, /web/database/selector)
# because with LIST_DB=False AND no DB created yet they return 404/5xx,
# which would fail the check on a fresh deploy.
# Any HTTP response (incl. 404) proves the worker is up.
# ============================================================
set -eu

# --max-time short, follow redirects, accept any 2xx/3xx/4xx as "alive".
# curl --fail-with-body returns 22 only on >=5xx; we treat <500 as healthy.
code=$(curl -s -o /dev/null --max-time 5 -w '%{http_code}' "http://localhost:8069/web/health" || echo 000)
[ "$code" != "000" ] && [ "$code" -lt 500 ] && exit 0
# Fallback: any response on /web/login (even 404) means HTTP server is alive
code=$(curl -s -o /dev/null --max-time 5 -w '%{http_code}' "http://localhost:8069/web/login" || echo 000)
[ "$code" != "000" ] && [ "$code" -lt 500 ] && exit 0
exit 1
