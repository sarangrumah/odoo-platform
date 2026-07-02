#!/usr/bin/env bash
# demo_wms / 00 — create the demo_wms database and install all WMS modules.
#
# Usage:
#   bash scripts/tenants/wms_demo/00_create_db.sh            # db name: demo_wms
#   bash scripts/tenants/wms_demo/00_create_db.sh my_db      # custom db name
#
# Creates a clean DB (no Odoo demo data) with the full WMS stack installed:
#   core   : stock, purchase, sale_management, product_expiry,
#            stock_picking_batch, barcodes, barcodes_gs1_nomenclature
#   custom : custom_barcode, custom_wms_putaway, custom_wms_cycle_count,
#            custom_wms_to_engine, custom_hht_bridge, custom_receipt_async
# (custom_core / custom_pdp_audit are pulled automatically via depends.)
set -euo pipefail

DB="${1:-demo_wms}"
ODOO=odoo19-platform-odoo-mgmt

MODULES="stock,purchase,sale_management,product_expiry,stock_picking_batch,\
barcodes,barcodes_gs1_nomenclature,custom_barcode,custom_wms_putaway,\
custom_wms_cycle_count,custom_wms_to_engine,custom_hht_bridge,custom_receipt_async"

echo ">>> Creating + initialising database '${DB}' (this can take a few minutes)"
docker exec -i "${ODOO}" odoo \
    -d "${DB}" \
    -i "${MODULES}" \
    --without-demo=all \
    --stop-after-init \
    --no-http

echo ">>> Database '${DB}' ready. Now run the seed scripts in order:"
echo "    for f in 10_seed_warehouse 20_seed_products 30_seed_inbound 40_seed_outbound 50_config_wms 99_verify; do"
echo "      docker exec -i ${ODOO} odoo shell -d ${DB} --no-http < scripts/tenants/wms_demo/\${f}.py"
echo "    done"
