#!/usr/bin/env bash
# Download official Odoo app icons for our custom_* modules.
#
# Maps custom_<x> → upstream Odoo module slug, fetches
# https://download.odoocdn.com/icons/<slug>/static/description/icon.png
# and drops it into addons/<group>/custom_<x>/static/description/icon.png.
#
# Modules with no upstream equivalent (Indonesia-specific or platform
# internal) are listed at the bottom and skipped — those need a
# bespoke icon (manual design or AI generation).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CDN="https://download.odoocdn.com/icons"

# custom_<name>:<odoo_module_slug>
MAPPING=(
    "custom_accounting_asset:account_asset"
    "custom_accounting_full:account_accountant"
    "custom_accounting_recurring:account_accountant"
    "custom_accounting_reports:account_reports"
    "custom_appointments:appointment"
    "custom_approval_engine:approvals"
    "custom_asset_from_receipt:account_asset"
    "custom_attendance:hr_attendance"
    "custom_bank_import:account_accountant"
    "custom_barcode:stock_barcode"
    "custom_crm:crm"
    "custom_dashboards:board"
    "custom_data_cleaning:data_cleaning"
    "custom_documents:documents"
    "custom_ecommerce:website_sale"
    "custom_elearning:website_slides"
    "custom_email_marketing:mass_mailing"
    "custom_events:website_event"
    "custom_expenses:hr_expense"
    "custom_field_service:industry_fsm"
    "custom_fleet_id:fleet"
    "custom_forum:website_forum"
    "custom_frontdesk:frontdesk"
    "custom_helpdesk:helpdesk"
    "custom_hr_appraisal:hr_appraisal"
    "custom_hr_leave_id:hr_holidays"
    "custom_hr_payroll_id:hr_payroll"
    "custom_hr_referral:hr_referral"
    "custom_iot_bridge:iot"
    "custom_knowledge:knowledge"
    "custom_livechat:im_livechat"
    "custom_lunch:lunch"
    "custom_maintenance:maintenance"
    "custom_marketing_automation:marketing_automation"
    "custom_mrp_plm:mrp_plm"
    "custom_payment_id:payment"
    "custom_planning:planning"
    "custom_pos_id:point_of_sale"
    "custom_quality_full:quality_control"
    "custom_recruitment_id:hr_recruitment"
    "custom_rental:sale_renting"
    "custom_repairs:repair"
    "custom_sign:sign"
    "custom_sms_id:mass_mailing_sms"
    "custom_social:social"
    "custom_spreadsheet:spreadsheet"
    "custom_studio_lite:web_studio"
    "custom_subscription:sale_subscription"
    "custom_survey:survey"
    "custom_tax_id:account_accountant"
    "custom_timesheet:hr_timesheet"
    "custom_todo:project_todo"
    "custom_voip:voip"
    "custom_whatsapp:whatsapp"
)

# Modules with NO upstream equivalent — need bespoke icons.
NEEDS_CUSTOM=(
    "custom_adapter_framework"
    "custom_ai_bridge"
    "custom_ai_features"
    "custom_bast"
    "custom_brd_analyzer"
    "custom_core"
    "custom_coretax"
    "custom_coretax_bupot"
    "custom_coretax_pajakku"
    "custom_dev_cycle"
    "custom_esg"
    "custom_hht_bridge"
    "custom_home_console"
    "custom_hub_console"
    "custom_onboarding_journey"
    "custom_ops_monitor"
    "custom_pdp_audit"
    "custom_pdp_consent"
    "custom_pdp_core"
    "custom_pdp_dsar"
    "custom_pdp_masking"
    "custom_pdp_retention"
    "custom_pph_witholding"
    "custom_super_admin"
    "custom_tenant_infra"
    "custom_wms_cycle_count"
    "custom_wms_putaway"
    "custom_wms_to_engine"
)

ok=0
fail=0
miss=0

find_module_dir() {
    local name="$1"
    find "$ROOT/addons" -mindepth 2 -maxdepth 2 -type d -name "$name" -print -quit
}

for pair in "${MAPPING[@]}"; do
    custom="${pair%%:*}"
    slug="${pair##*:}"
    dir="$(find_module_dir "$custom")"
    if [[ -z "$dir" ]]; then
        echo "  miss   $custom (module folder not found)"
        miss=$((miss + 1))
        continue
    fi
    mkdir -p "$dir/static/description"
    out="$dir/static/description/icon.png"
    if curl -fsS -o "$out" "$CDN/$slug/static/description/icon.png"; then
        size=$(stat -c %s "$out" 2>/dev/null || stat -f %z "$out")
        echo "  ok     $custom <- $slug (${size}B)"
        ok=$((ok + 1))
    else
        echo "  FAIL   $custom <- $slug (CDN miss)"
        rm -f "$out"
        fail=$((fail + 1))
    fi
done

echo
echo "Downloaded: $ok    Failed: $fail    Missing folder: $miss"
echo "Bespoke needed (${#NEEDS_CUSTOM[@]}):"
for m in "${NEEDS_CUSTOM[@]}"; do
    dir="$(find_module_dir "$m")"
    [[ -n "$dir" ]] && echo "  $m  ->  $dir/static/description/icon.png"
done
