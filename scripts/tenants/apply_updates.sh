#!/usr/bin/env bash
# Apply repo changes to every tenant DB.
#
# Strategy:
#   1. For schema/data managed by Odoo modules → odoo -u <modules> -d <db>.
#   2. For raw SQL seeds (e.g. custom_pdp_audit) → psql -f, idempotent.
#
# Run AFTER `git pull` AND AFTER restarting the Odoo container
# (Python re-import doesn't happen on `make update` alone — see
# memory: feedback_odoo_module_deploy).
#
# Usage:
#   bash scripts/tenants/apply_updates.sh              # all tenant DBs
#   bash scripts/tenants/apply_updates.sh era_busana_retailindo  # one
#
# Requires: docker compose stack up; psql reachable as ${PG_USER}@${PG_HOST}.

set -euo pipefail

PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-odoo}"
ODOO_SERVICE="${ODOO_SERVICE:-odoo}"
COMPOSE="${COMPOSE:-docker compose}"

# Modules whose -u should be re-run on every tenant after this batch of commits.
MODULES_TO_UPDATE=(
  custom_coretax
  custom_pdp_masking
  custom_pdp_audit
  custom_ai_bridge
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

# Raw SQL seeds (idempotent — safe to re-apply).
SQL_SEEDS=(
  "addons/compliance/custom_pdp_audit/data/02-pdp-schema.sql"
)

list_tenant_dbs() {
  PGPASSWORD="${PGPASSWORD:-}" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -tAc \
    "SELECT datname FROM pg_database
     WHERE datistemplate = false
       AND datname NOT IN ('postgres','odoo_mgmt');"
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
    if [[ -f "$sql" ]]; then
      PGPASSWORD="${PGPASSWORD:-}" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$db" -v ON_ERROR_STOP=1 -f "$sql"
    else
      echo "WARN: $sql not found, skipping"
    fi
  done
}

main() {
  if [[ $# -gt 0 ]]; then
    dbs=("$@")
  else
    mapfile -t dbs < <(list_tenant_dbs)
  fi

  if [[ ${#dbs[@]} -eq 0 ]]; then
    echo "No tenant DBs found."
    exit 0
  fi

  for db in "${dbs[@]}"; do
    apply_to_db "$db"
  done

  echo
  echo "Done. Applied to: ${dbs[*]}"
}

main "$@"
