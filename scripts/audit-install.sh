#!/usr/bin/env bash
# Iterate every uninstalled custom module, try to install, capture outcome.
# Usage: bash scripts/audit-install.sh
set -u

DB="${DB:-smoke_test}"
OUT="${OUT:-/tmp/odoo-install-audit}"
mkdir -p "$OUT"
SUMMARY="$OUT/summary.txt"
> "$SUMMARY"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.dev.yml"

modules=(
  custom_accounting_full
  custom_ai_features
  custom_appointments
  custom_approval_engine
  custom_coretax_pajakku
  custom_documents
  custom_field_service
  custom_hr_appraisal
  custom_hr_referral
  custom_iot_bridge
  custom_marketing_automation
  custom_mrp_plm
  custom_planning
  custom_quality_full
  custom_rental
  custom_sign
  custom_social
  custom_studio_lite
  custom_super_admin
  custom_tax_id
  custom_voip
)

for m in "${modules[@]}"; do
  echo "=========================================="
  echo "Installing $m..."
  LOG="$OUT/$m.log"
  $COMPOSE exec -T odoo odoo -d "$DB" -i "$m" --stop-after-init --without-demo=all > "$LOG" 2>&1

  if grep -q "Registry loaded" "$LOG" && ! grep -q "Failed to load registry" "$LOG"; then
    echo "  OK"
    echo "OK  $m" >> "$SUMMARY"
  else
    # Extract first meaningful error line
    err=$(grep -E "ValueError|TypeError|psycopg2\.errors|ParseError|odoo\.exceptions" "$LOG" | head -1 | sed 's/^.*ERROR/ERROR/;s|.*Traceback.*||' | cut -c1-200)
    if [ -z "$err" ]; then
      err=$(grep -E "ERROR|CRITICAL" "$LOG" | head -2 | tail -1 | cut -c1-200)
    fi
    echo "  FAIL: $err"
    echo "FAIL  $m  ::  $err" >> "$SUMMARY"
    # Clean up failed state so next install isn't blocked
    $COMPOSE exec -T -e PGPASSWORD=PgPasswordSmokeTest1234 postgres psql -U odoo -d "$DB" -c "UPDATE ir_module_module SET state='uninstalled' WHERE name='$m' AND state IN ('to install','to upgrade');" >/dev/null 2>&1 || true
  fi
done

echo "=========================================="
echo "Summary:"
cat "$SUMMARY"
