#!/usr/bin/env bash
# ============================================================
# Odoo healthcheck — minimal HTTP probe to /web/database/selector
# Returns 0 if Odoo HTTP is reachable.
# ============================================================
set -eu

URL="http://localhost:8069/web/database/selector"
curl -fsS -o /dev/null --max-time 5 "$URL" \
  || curl -fsS -o /dev/null --max-time 5 "http://localhost:8069/web/login" \
  || exit 1
