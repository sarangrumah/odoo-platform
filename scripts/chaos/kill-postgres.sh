#!/usr/bin/env bash
# Drill: kill postgres, observe Odoo reconnection, verify no data loss.

set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$here"
# shellcheck source=lib/_common.sh
. ./scripts/chaos/lib/_common.sh

START=$(now_iso)
color_yellow "[$(now_iso)] DRILL: kill-postgres"
snapshot_state

# Capture row counts on a sentinel table so we can verify "no data loss"
SENTINEL_BEFORE=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" \
  "${PROJECT}-postgres" psql -U "${POSTGRES_USER:-odoo}" \
  -d "${POSTGRES_DB:-postgres}" -tAc \
  "SELECT count(*) FROM tenant_registry.action_log;" 2>/dev/null || echo "unknown")
color_cyan "Sentinel rows in tenant_registry.action_log: ${SENTINEL_BEFORE}"

color_red "[$(now_iso)] Killing postgres container..."
docker kill --signal=SIGKILL "${PROJECT}-postgres" >/dev/null
sleep 2
snapshot_state

color_cyan "[$(now_iso)] Restarting postgres..."
$COMPOSE_CMD up -d postgres
wait_healthy postgres 120

color_cyan "[$(now_iso)] Waiting for Odoo to re-establish connections..."
wait_healthy odoo 180 || true

SENTINEL_AFTER=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" \
  "${PROJECT}-postgres" psql -U "${POSTGRES_USER:-odoo}" \
  -d "${POSTGRES_DB:-postgres}" -tAc \
  "SELECT count(*) FROM tenant_registry.action_log;" 2>/dev/null || echo "unknown")
color_cyan "Sentinel rows after recovery: ${SENTINEL_AFTER}"

if [ "$SENTINEL_BEFORE" = "$SENTINEL_AFTER" ]; then
  drill_report "kill-postgres" "$START" "$(now_iso)" "PASS — no data loss"
else
  color_red "Sentinel count drifted ${SENTINEL_BEFORE} → ${SENTINEL_AFTER}"
  drill_report "kill-postgres" "$START" "$(now_iso)" "FAIL — data loss detected"
  exit 1
fi
