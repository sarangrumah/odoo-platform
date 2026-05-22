#!/usr/bin/env bash
# Verify the master-DB tenant_registry.action_log hash chain.
# Returns 0 + empty output if chain is intact; rows if broken.

set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

# shellcheck disable=SC1091
if [ -f .env ]; then set -a; . .env; set +a; fi

container="${COMPOSE_PROJECT_NAME:-odoo19-platform}-postgres"
db="${POSTGRES_DB:-postgres}"
user="${POSTGRES_USER:-odoo}"

docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD}" "$container" \
  psql -U "$user" -d "$db" -F $'\t' -A -t \
  -c "SELECT * FROM tenant_registry.verify_action_chain();"
