#!/usr/bin/env bash
# Drill: kill ai-gateway, verify Odoo AI features degrade gracefully.

set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$here"
. ./scripts/chaos/lib/_common.sh

START=$(now_iso)
color_yellow "[$(now_iso)] DRILL: kill-ai-gateway"
snapshot_state

color_red "[$(now_iso)] Killing ai-gateway..."
docker kill --signal=SIGKILL "${PROJECT}-ai-gateway" >/dev/null
sleep 1

# Verify Odoo itself still serves requests
color_cyan "[$(now_iso)] Probing Odoo health..."
status=$(curl -s -o /dev/null -w "%{http_code}" \
  "http://localhost:${ODOO_HTTP_PORT:-18069}/web/database/list" || echo "ERR")
echo "  Odoo HTTP /web/database/list: $status"
if [ "$status" != "200" ] && [ "$status" != "403" ]; then
  color_red "Odoo appears broken without ai-gateway — investigate cross-coupling."
fi

# Bring ai-gateway back
color_cyan "[$(now_iso)] Restarting ai-gateway..."
$COMPOSE_CMD up -d ai-gateway
wait_healthy ai-gateway 60

drill_report "kill-ai-gateway" "$START" "$(now_iso)" \
  "Verify Ask-AI widget showed graceful error message during downtime."
