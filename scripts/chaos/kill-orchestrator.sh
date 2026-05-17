#!/usr/bin/env bash
# Drill: kill tenant-orchestrator, verify super-admin UI surfaces error
# without affecting tenant runtime.

set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$here"
. ./scripts/chaos/lib/_common.sh

START=$(now_iso)
color_yellow "[$(now_iso)] DRILL: kill-tenant-orchestrator"
snapshot_state

color_red "[$(now_iso)] Killing tenant-orchestrator..."
docker kill --signal=SIGKILL "${PROJECT}-tenant-orchestrator" >/dev/null
sleep 1

# Probe each tenant URL to confirm runtime is unaffected
slugs="${TENANT_SLUGS:-acme}"
for slug in $(echo "$slugs" | tr ',' ' '); do
  url="https://${slug}.platform.localhost/web/login"
  status=$(curl -sk -o /dev/null -w "%{http_code}" "$url" || echo "ERR")
  echo "  ${url}: HTTP $status"
done

color_cyan "[$(now_iso)] Restarting tenant-orchestrator..."
$COMPOSE_CMD up -d tenant-orchestrator
wait_healthy tenant-orchestrator 60

drill_report "kill-orchestrator" "$START" "$(now_iso)" \
  "Tenant runtime should stay 200/302; only lifecycle ops (provision/suspend) fail during downtime."
