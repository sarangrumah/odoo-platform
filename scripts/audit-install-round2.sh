#!/usr/bin/env bash
# Retry install on modules that had shallow fixes applied.
set -u

DB="${DB:-smoke_test}"
OUT="${OUT:-/tmp/odoo-install-audit}"
SUMMARY="$OUT/summary-round2.txt"
> "$SUMMARY"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.dev.yml"

modules=(
  custom_ai_features
  custom_approval_engine
  custom_coretax_pajakku
  custom_marketing_automation
  custom_social
  custom_super_admin
  custom_voip
)

for m in "${modules[@]}"; do
  echo "=========================================="
  echo "Installing $m..."
  LOG="$OUT/$m.r2.log"
  $COMPOSE exec -T odoo odoo -d "$DB" -i "$m" --stop-after-init --without-demo=all > "$LOG" 2>&1

  if grep -q "Registry loaded" "$LOG" && ! grep -q "Failed to load registry" "$LOG"; then
    echo "  OK"
    echo "OK  $m" >> "$SUMMARY"
  else
    err=$(grep -E "ValueError:|TypeError:|psycopg2\.errors|ParseError:|ValidationError:" "$LOG" | head -1 | cut -c1-200)
    if [ -z "$err" ]; then
      err=$(grep -E "ERROR|CRITICAL" "$LOG" | head -2 | tail -1 | cut -c1-200)
    fi
    echo "  FAIL: $err"
    echo "FAIL  $m  ::  $err" >> "$SUMMARY"
    $COMPOSE exec -T -e PGPASSWORD=PgPasswordSmokeTest1234 postgres psql -U odoo -d "$DB" -c "UPDATE ir_module_module SET state='uninstalled' WHERE name='$m' AND state IN ('to install','to upgrade');" >/dev/null 2>&1 || true
  fi
done

echo "=========================================="
echo "Round 2 Summary:"
cat "$SUMMARY"
