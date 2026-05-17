#!/usr/bin/env bash
# Automated compliance verifier — runs every check listed in
# docs/compliance/soc2-controls.md § Automated Verification.
#
# Emits a structured JSON report at docs/compliance/_last_verify.json
# AND prints a coloured summary. Exit code: 0 all pass, 1 any fail.

set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$here"

if [ -f .env ]; then set -a; . .env; set +a; fi

PROJECT="${COMPOSE_PROJECT_NAME:-odoo19-platform}"
PG_USER="${POSTGRES_USER:-odoo}"
PG_PWD="${POSTGRES_PASSWORD}"
PG_DB_MASTER="${POSTGRES_DB:-postgres}"
PG_CONTAINER="${PROJECT}-postgres"

color_red()   { printf '\033[31m%s\033[0m' "$*"; }
color_green() { printf '\033[32m%s\033[0m' "$*"; }
color_amber() { printf '\033[33m%s\033[0m' "$*"; }
mark_pass()   { echo "  $(color_green '✓') $*"; }
mark_fail()   { echo "  $(color_red '✗') $*"; FAIL=1; }
mark_warn()   { echo "  $(color_amber '!') $*"; }

FAIL=0
REPORT="docs/compliance/_last_verify.json"
mkdir -p "$(dirname "$REPORT")"
{
  echo "{"
  echo "  \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
  echo "  \"checks\": ["
} > "$REPORT"

emit_json() {
  local id="$1" status="$2" message="$3"
  message="${message//\"/\\\"}"
  echo "    {\"id\": \"$id\", \"status\": \"$status\", \"message\": \"$message\"}${4:+,}" >> "$REPORT"
}

run_psql() {
  docker exec -e PGPASSWORD="$PG_PWD" "$PG_CONTAINER" \
    psql -U "$PG_USER" -d "$1" -tAc "$2" 2>/dev/null
}

list_tenant_dbs() {
  run_psql "$PG_DB_MASTER" \
    "SELECT db_name FROM tenant_registry.tenants WHERE state = 'active' ORDER BY db_name;" \
    | tr -d '\r'
}

echo "== Compliance Verification =="
echo

# ----- 1. Master action_log chain -----
echo "1. tenant_registry.action_log chain"
broken=$(run_psql "$PG_DB_MASTER" "SELECT COUNT(*) FROM tenant_registry.verify_action_chain();")
if [ "${broken:-0}" = "0" ]; then
  mark_pass "Master action_log chain intact"
  emit_json "master_action_log_chain" "pass" "0 broken rows" ","
else
  mark_fail "Master action_log chain has $broken broken rows"
  emit_json "master_action_log_chain" "fail" "$broken broken rows" ","
fi

# ----- 2. Per-tenant pdp.audit_log chain -----
echo "2. pdp.audit_log chain (per tenant)"
tenants=$(list_tenant_dbs)
if [ -z "$tenants" ]; then
  mark_warn "No active tenants — skipping per-tenant chain check"
  emit_json "per_tenant_chain" "warn" "no active tenants" ","
else
  any_fail=0
  for db in $tenants; do
    rows=$(run_psql "$db" "SELECT COUNT(*) FROM pdp.verify_audit_chain();" 2>/dev/null || echo "ERR")
    if [ "$rows" = "0" ]; then
      mark_pass "  $db: chain intact"
    else
      mark_fail "  $db: $rows broken rows"
      any_fail=1
    fi
  done
  if [ "$any_fail" = "0" ]; then
    emit_json "per_tenant_chain" "pass" "all tenants verified" ","
  else
    emit_json "per_tenant_chain" "fail" "one or more tenants broken" ","
  fi
fi

# ----- 3. Coverage: posted moves vs audit log (30d) -----
echo "3. Audit coverage — posted account.move vs pdp.audit_log (30d)"
if [ -n "$tenants" ]; then
  any_warn=0
  for db in $tenants; do
    posted=$(run_psql "$db" \
      "SELECT COUNT(*) FROM account_move WHERE state='posted' AND write_date > now() - interval '30 days';" 2>/dev/null || echo "0")
    logged=$(run_psql "$db" \
      "SELECT COUNT(*) FROM pdp.audit_log WHERE model_name='account.move' AND ts > now() - interval '30 days';" 2>/dev/null || echo "0")
    if [ "$logged" -ge "$posted" ]; then
      mark_pass "  $db: $logged log entries ≥ $posted posted moves"
    else
      mark_warn "  $db: only $logged log entries for $posted posted moves"
      any_warn=1
    fi
  done
  emit_json "audit_coverage_moves" "$([ $any_warn = 0 ] && echo pass || echo warn)" "see per-tenant detail" ","
else
  emit_json "audit_coverage_moves" "warn" "skipped (no tenants)" ","
fi

# ----- 4. Encryption at rest: master wrapping key set -----
echo "4. Master KMS wrapping key present"
if [ -n "${MASTER_WRAPPING_KEY:-}" ] && [ "${MASTER_WRAPPING_KEY}" != *"changeme"* ]; then
  mark_pass "MASTER_WRAPPING_KEY env var set + non-default"
  emit_json "master_wrapping_key" "pass" "env var set" ","
else
  mark_fail "MASTER_WRAPPING_KEY missing or default — sertel + DEKs cannot be wrapped"
  emit_json "master_wrapping_key" "fail" "missing or default" ","
fi

# ----- 5. Per-tenant retention policy presence -----
echo "5. PDP retention policies"
if [ -n "$tenants" ]; then
  any_warn=0
  for db in $tenants; do
    n=$(run_psql "$db" "SELECT COUNT(*) FROM pdp_retention_policy WHERE active=true;" 2>/dev/null || echo "0")
    if [ "$n" -gt 0 ]; then
      mark_pass "  $db: $n active retention policies"
    else
      mark_warn "  $db: NO active retention policies (UU 27/2022 art.25)"
      any_warn=1
    fi
  done
  emit_json "retention_policies" "$([ $any_warn = 0 ] && echo pass || echo warn)" "see per-tenant detail" ","
else
  emit_json "retention_policies" "warn" "skipped (no tenants)" ","
fi

# ----- 6. Pajakku transactions: errors vs successes (rolling 7d) -----
echo "6. Pajakku adapter health (7d)"
if [ -n "$tenants" ]; then
  for db in $tenants; do
    counts=$(run_psql "$db" \
      "SELECT state, COUNT(*) FROM custom_coretax_transaction WHERE create_date > now() - interval '7 days' GROUP BY state;" 2>/dev/null || true)
    if [ -n "$counts" ]; then
      mark_pass "  $db: $(echo "$counts" | tr '\n' '; ')"
    fi
  done
  emit_json "pajakku_health" "info" "7d transaction counts logged" ","
fi

# ----- 7. Backup recency -----
echo "7. Backup recency (last 25h)"
recent=$(run_psql "$PG_DB_MASTER" \
  "SELECT COUNT(DISTINCT tenant_id) FROM tenant_registry.backups
   WHERE outcome='success' AND finished_at > now() - interval '25 hours';")
total=$(run_psql "$PG_DB_MASTER" \
  "SELECT COUNT(*) FROM tenant_registry.tenants WHERE state='active';")
if [ "$recent" = "$total" ] && [ "${total:-0}" -gt 0 ]; then
  mark_pass "All $total active tenants have a backup < 25h old"
  emit_json "backup_recency" "pass" "$recent/$total" ","
else
  mark_warn "$recent/$total tenants have a recent backup"
  emit_json "backup_recency" "warn" "$recent/$total" ","
fi

# ----- 8. Service health -----
echo "8. Service health (docker compose)"
unhealthy=$(docker ps --filter "name=${PROJECT}-" --format '{{.Names}}\t{{.Status}}' \
  | grep -v '(healthy)' | grep -v 'Up' | wc -l || echo "0")
unhealthy=$(echo "$unhealthy" | tr -d '[:space:]')
if [ "$unhealthy" = "0" ]; then
  mark_pass "All services healthy"
  emit_json "service_health" "pass" "all healthy" ""
else
  mark_fail "$unhealthy service(s) unhealthy"
  emit_json "service_health" "fail" "$unhealthy unhealthy" ""
fi

# ----- finalize JSON -----
{
  echo "  ],"
  echo "  \"fail\": $FAIL"
  echo "}"
} >> "$REPORT"

echo
if [ "$FAIL" = "0" ]; then
  color_green "PASS — report at $REPORT"; echo
  exit 0
else
  color_red "FAIL — report at $REPORT"; echo
  exit 1
fi
