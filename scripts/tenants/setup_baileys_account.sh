#!/usr/bin/env bash
# Provision a Baileys WhatsApp account in one or many tenant DBs.
#
# Idempotent: if a whatsapp.account record with the same name already
# exists in the target DB it is left untouched (existing secret is NOT
# overwritten — rotate it via the UI if you need to).
#
# Usage:
#   bash scripts/tenants/setup_baileys_account.sh <db>            # one
#   bash scripts/tenants/setup_baileys_account.sh                 # all tenants
#
# Env overrides:
#   COMPOSE              (default "docker compose")
#   ODOO_SERVICE         (default "odoo")
#   DB_SERVICE           (default "postgres")
#   PG_USER              (default $POSTGRES_USER or "odoo")
#   PG_MAINTENANCE_DB    (default "postgres")
#   SKIP_DBS             (comma-separated, default "postgres,odoo_mgmt,template0,template1")
#   ACCOUNT_NAME         (default "Main Baileys")
#   BAILEYS_INTERNAL_URL (default "http://baileys:8088")
#   BAILEYS_SHARED_SECRET   REQUIRED — must match the baileys service env.
#
# After this script: open Apps → whatsapp.account → Start Session → scan QR.

set -euo pipefail

COMPOSE="${COMPOSE:-docker compose}"
ODOO_SERVICE="${ODOO_SERVICE:-odoo}"
DB_SERVICE="${DB_SERVICE:-postgres}"
PG_USER="${PG_USER:-${POSTGRES_USER:-odoo}}"
PG_MAINTENANCE_DB="${PG_MAINTENANCE_DB:-postgres}"
SKIP_DBS="${SKIP_DBS:-postgres,odoo_mgmt,template0,template1}"
ACCOUNT_NAME="${ACCOUNT_NAME:-Main Baileys}"
BAILEYS_INTERNAL_URL="${BAILEYS_INTERNAL_URL:-http://baileys:8088}"

if [[ -z "${BAILEYS_SHARED_SECRET:-}" ]]; then
  echo "ERROR: BAILEYS_SHARED_SECRET env var is required." >&2
  echo "       Generate one with: openssl rand -hex 32" >&2
  echo "       It MUST match the value in the baileys service env." >&2
  exit 2
fi

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
  ${COMPOSE} exec -T "$DB_SERVICE" \
    psql -U "$PG_USER" -d "$PG_MAINTENANCE_DB" -tAc \
    "SELECT datname FROM pg_database
     WHERE datistemplate = false
       AND datname NOT IN ($(sql_skip_list));"
}

provision_db() {
  local db="$1"
  local session_id="acct-${db}"
  echo "=== [$db] provisioning Baileys account '${ACCOUNT_NAME}' ==="

  ${COMPOSE} exec -T \
    -e BAILEYS_ACCOUNT_NAME="$ACCOUNT_NAME" \
    -e BAILEYS_INTERNAL_URL="$BAILEYS_INTERNAL_URL" \
    -e BAILEYS_SHARED_SECRET="$BAILEYS_SHARED_SECRET" \
    -e BAILEYS_SESSION_ID="$session_id" \
    "$ODOO_SERVICE" odoo shell -d "$db" --no-http --stop-after-init <<'PYEOF'
import os
name = os.environ["BAILEYS_ACCOUNT_NAME"]
existing = env["whatsapp.account"].sudo().search([("name", "=", name)], limit=1)
if existing:
    print(f"[skip] whatsapp.account id={existing.id} name={name!r} already exists; leaving untouched.")
else:
    rec = env["whatsapp.account"].sudo().create({
        "name": name,
        "provider": "baileys",
        "is_active": True,
        "sandbox_mode": False,
        "baileys_sidecar_url": os.environ["BAILEYS_INTERNAL_URL"],
        "baileys_shared_secret": os.environ["BAILEYS_SHARED_SECRET"],
        "baileys_session_id": os.environ["BAILEYS_SESSION_ID"],
    })
    env.cr.commit()
    print(f"[ok] created whatsapp.account id={rec.id} name={name!r} session={rec.baileys_session_id}")
PYEOF
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

  echo "Will provision Baileys account in: ${dbs[*]}"
  for db in "${dbs[@]}"; do
    provision_db "$db"
  done

  echo
  echo "Done. Next step: open Apps → WhatsApp Accounts → Start Session → scan QR."
}

main "$@"
