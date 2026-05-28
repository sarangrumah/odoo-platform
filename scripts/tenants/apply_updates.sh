#!/usr/bin/env bash
# Apply repo changes to every tenant DB.
#
# Strategy:
#   1. For schema/data managed by Odoo modules → odoo -u <modules> -d <db>.
#   2. For raw SQL seeds (e.g. custom_pdp_audit) → psql -f, idempotent.
#
# Runs psql + odoo INSIDE the compose containers — host doesn't need
# psql installed. Postgres is reached via `docker compose exec postgres
# psql` and Odoo via `docker compose exec odoo odoo`.
#
# Run AFTER `git pull` AND AFTER restarting the Odoo container
# (Python re-import doesn't happen on `make update` alone — see
# memory: feedback_odoo_module_deploy).
#
# Usage:
#   bash scripts/tenants/apply_updates.sh              # all tenant DBs
#   bash scripts/tenants/apply_updates.sh era_busana_retailindo  # one
#
# Env overrides:
#   COMPOSE          (default "docker compose")
#   ODOO_SERVICE     (default "odoo")
#   DB_SERVICE       (default "postgres")
#   PG_USER          (default $POSTGRES_USER or "odoo")
#   PG_MAINTENANCE_DB (default "postgres" — used to list DBs)
#   SKIP_DBS         (comma-separated, default "postgres,odoo_mgmt,template0,template1")

set -euo pipefail

COMPOSE="${COMPOSE:-docker compose}"
ODOO_SERVICE="${ODOO_SERVICE:-odoo}"
DB_SERVICE="${DB_SERVICE:-postgres}"
PG_USER="${PG_USER:-${POSTGRES_USER:-odoo}}"
PG_MAINTENANCE_DB="${PG_MAINTENANCE_DB:-postgres}"
SKIP_DBS="${SKIP_DBS:-postgres,odoo_mgmt,template0,template1}"

# Source repo .env so PGPASSWORD / POSTGRES_PASSWORD reach docker exec.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -z "${PGPASSWORD:-}" && -z "${POSTGRES_PASSWORD:-}" && -f "${REPO_ROOT}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a; . "${REPO_ROOT}/.env"; set +a
fi
PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"

MODULES_TO_UPDATE=(
  custom_coretax
  custom_pdp_masking
  custom_pdp_audit
  custom_ai_bridge
  custom_whatsapp
  custom_rental
  custom_rental_bom_explosion
  custom_rental_invoicing
  custom_rental_quality_hook
  custom_studio_lite
  custom_accounting_full
  custom_accounting_asset
  custom_asset_from_receipt
  custom_receipt_async
  custom_intercompany_procurement
  custom_dashboards
  custom_hub_console
  custom_home_console
  custom_expenses
  custom_wms_cycle_count
  custom_wms_putaway
  l10n_id_psak_custom
)

# Raw SQL seeds (idempotent — safe to re-apply). Paths INSIDE the
# odoo container under /mnt/extra-addons (default). Override
# CONTAINER_REPO_ROOT if your mount path differs.
CONTAINER_REPO_ROOT="${CONTAINER_REPO_ROOT:-/mnt/extra-addons}"
SQL_SEEDS=(
  "addons/compliance/custom_pdp_audit/data/02-pdp-schema.sql"
)

# Convert SKIP_DBS into a SQL NOT IN list.
sql_skip_list() {
  local IFS=','
  local out=""
  for d in $SKIP_DBS; do
    [[ -n "$out" ]] && out+=","
    out+="'$d'"
  done
  echo "$out"
}

list_tenant_dbs() {
  ${COMPOSE} exec -T -e PGPASSWORD="$PGPASSWORD" "$DB_SERVICE" \
    psql -U "$PG_USER" -d "$PG_MAINTENANCE_DB" -tAc \
    "SELECT datname FROM pg_database
     WHERE datistemplate = false
       AND datname NOT IN ($(sql_skip_list));"
}

apply_to_db() {
  local db="$1"
  echo "=== [$db] applying module updates ==="
  ${COMPOSE} exec -T "$ODOO_SERVICE" odoo \
    -d "$db" \
    -u "$(IFS=,; echo "${MODULES_TO_UPDATE[*]}")" \
    --stop-after-init \
    --no-http

  echo "=== [$db] applying raw SQL seeds ==="
  for sql in "${SQL_SEEDS[@]}"; do
    # Pipe host-side file into the postgres container — works even
    # if the repo isn't mounted into the db service.
    if [[ -f "$sql" ]]; then
      ${COMPOSE} exec -T -e PGPASSWORD="$PGPASSWORD" "$DB_SERVICE" \
        psql -U "$PG_USER" -d "$db" -v ON_ERROR_STOP=1 < "$sql"
    else
      echo "WARN: $sql not found on host, skipping"
    fi
  done
}

main() {
  local dbs=()
  if [[ $# -gt 0 ]]; then
    dbs=("$@")
  else
    mapfile -t dbs < <(list_tenant_dbs | sed '/^$/d')
  fi

  if [[ ${#dbs[@]} -eq 0 ]]; then
    echo "No tenant DBs found (skip list: $SKIP_DBS)."
    exit 0
  fi

  echo "Will apply updates to: ${dbs[*]}"
  for db in "${dbs[@]}"; do
    apply_to_db "$db"
  done

  echo
  echo "Done. Applied to: ${dbs[*]}"
}

main "$@"
