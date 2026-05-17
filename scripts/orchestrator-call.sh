#!/usr/bin/env bash
# ============================================================
# orchestrator-call.sh — HMAC-signed curl wrapper for the
#                        tenant-orchestrator REST API.
#
# Usage:
#   ./orchestrator-call.sh GET /v1/tenants
#   ./orchestrator-call.sh POST /v1/tenants '{"slug":"acme","display_name":"Acme"}'
#   ./orchestrator-call.sh POST /v1/tenants/acme/suspend '{"reason":"maintenance"}'
#
# Required env (sourced from .env):
#   ORCHESTRATOR_SHARED_SECRET
#   TENANT_ORCHESTRATOR_PORT  (default 18091)
#   ORCHESTRATOR_URL          (default http://localhost:<port>)
# ============================================================

set -euo pipefail

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a
  . .env
  set +a
fi

: "${ORCHESTRATOR_SHARED_SECRET:?Set ORCHESTRATOR_SHARED_SECRET}"
ORCHESTRATOR_URL="${ORCHESTRATOR_URL:-http://localhost:${TENANT_ORCHESTRATOR_PORT:-18091}}"

method="${1:-GET}"
path="${2:?Usage: $0 METHOD /v1/path [BODY_JSON]}"
body="${3:-}"

ts=$(date +%s)
payload="${ts}.${body}"
sig=$(printf '%s' "$payload" | openssl dgst -sha256 -hmac "$ORCHESTRATOR_SHARED_SECRET" -hex | awk '{print $NF}')

actor="${USER:-cli}@$(hostname)"

if [ -n "$body" ]; then
  curl -sS -X "$method" "${ORCHESTRATOR_URL}${path}" \
    -H "Content-Type: application/json" \
    -H "X-Custom-Signature: t=${ts},v1=${sig}" \
    -H "X-Custom-Actor: ${actor}" \
    -d "$body"
else
  curl -sS -X "$method" "${ORCHESTRATOR_URL}${path}" \
    -H "X-Custom-Signature: t=${ts},v1=${sig}" \
    -H "X-Custom-Actor: ${actor}"
fi
echo
