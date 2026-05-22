#!/bin/sh
# ============================================================
# 05 — Rotate tenant_orchestrator role password from env var
# ============================================================
# 04-tenant-registry-schema.sql creates `tenant_orchestrator` with a
# placeholder password. This script (which runs after 04 because of
# alphabetical ordering in /docker-entrypoint-initdb.d/) sets the real
# password from the PG_ORCHESTRATOR_PASSWORD env var.
#
# Postgres init scripts only run on FIRST boot (empty data dir). For
# password rotation on an existing cluster, use:
#   make rotate-orchestrator-pwd
# ============================================================

set -e

if [ -z "$PG_ORCHESTRATOR_PASSWORD" ]; then
  echo "WARNING: PG_ORCHESTRATOR_PASSWORD not set — tenant_orchestrator role keeps placeholder password (unusable)" >&2
  exit 0
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  ALTER ROLE tenant_orchestrator WITH LOGIN PASSWORD '$PG_ORCHESTRATOR_PASSWORD';
EOSQL

echo "tenant_orchestrator password rotated from env."
