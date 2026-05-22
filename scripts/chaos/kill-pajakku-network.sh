#!/usr/bin/env bash
# Drill: block outbound HTTPS to Pajakku to trigger circuit breaker.
# Implemented as a DNS override that points api.pajakku.com → 127.0.0.1
# inside the ai-gateway container (which is where the Pajakku adapter
# runs from). Reverses after HOLD_SECONDS.

set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$here"
. ./scripts/chaos/lib/_common.sh

HOLD_SECONDS="${HOLD_SECONDS:-120}"
TARGET_HOST="${TARGET_HOST:-api.pajakku.com sandbox-api.pajakku.com}"

START=$(now_iso)
color_yellow "[$(now_iso)] DRILL: kill-pajakku-network (block ${TARGET_HOST} for ${HOLD_SECONDS}s)"

CONTAINER="${PROJECT}-tenant-orchestrator"
# The Pajakku adapter actually runs inside Odoo since it's an Odoo model.
ODOO_CONTAINER="${PROJECT}-odoo"

snapshot_state

color_red "Adding /etc/hosts override inside ${ODOO_CONTAINER}..."
for host in $TARGET_HOST; do
  docker exec --user root "$ODOO_CONTAINER" sh -c \
    "echo '127.0.0.1 ${host}' >> /etc/hosts"
done

color_cyan "Block active. Trigger Pajakku submissions from the UI now."
color_cyan "Watch tenant_registry.action_log for coretax_pajakku_error rows + circuit breaker open notification."
sleep "$HOLD_SECONDS"

color_green "Reverting /etc/hosts..."
for host in $TARGET_HOST; do
  docker exec --user root "$ODOO_CONTAINER" sh -c \
    "sed -i '/${host}/d' /etc/hosts"
done

drill_report "kill-pajakku-network" "$START" "$(now_iso)" \
  "Verify breaker opened at 10 failures + mail.thread notification posted on coretax config."
