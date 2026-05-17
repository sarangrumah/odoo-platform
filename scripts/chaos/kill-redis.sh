#!/usr/bin/env bash
# Drill: kill redis, observe ai-gateway rate-limit fail-open.

set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$here"
. ./scripts/chaos/lib/_common.sh

START=$(now_iso)
color_yellow "[$(now_iso)] DRILL: kill-redis"
snapshot_state

color_red "[$(now_iso)] Killing redis..."
docker kill --signal=SIGKILL "${PROJECT}-redis" >/dev/null
sleep 1

# Probe ai-gateway: a chat request should still succeed (HMAC-signed),
# rate-limit fails open with a warn log.
color_cyan "[$(now_iso)] Probing ai-gateway /health (must stay 200)..."
for i in 1 2 3 4 5; do
  status=$(curl -s -o /dev/null -w "%{http_code}" \
    "http://localhost:${AI_GATEWAY_PORT:-18080}/health" || echo "ERR")
  echo "  attempt $i: HTTP $status"
  sleep 2
done

color_cyan "[$(now_iso)] Restarting redis..."
$COMPOSE_CMD up -d redis
wait_healthy redis 60

drill_report "kill-redis" "$START" "$(now_iso)" \
  "Verify ai-gateway logs include ratelimit.redis_error warning during downtime."
