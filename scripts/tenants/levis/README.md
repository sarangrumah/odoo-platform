# Levi's (PT Sinar Eka Selaras) — data onboarding runbook

Tenant DB: `levis`. Source files: `docs/levis/`. This folder is **Track A** (ops
scripts for fast go-live). The durable, reusable adapter is the **Track B** module
`addons/ee_gap/custom_retail_import` (Excel/CSV upload wizard + SFTP feed).

## ⚠️ Data reality check (verified 2026-06-11)
The X-prefix transaction files currently delivered are **single-store SAMPLES** —
they only contain store **14694 "OLS SCU - TUNJUNGAN PLAZA 3"**:
- `X20` on-hand, `X24DN` sales, `X70D` tenders → all 1 store only.
- `X101` products (159,658 SKUs) and `CoA EBR` are **full** and ready.
- `Store Master` lists all **24 stores** (1 DC + 23 OLS) **by name, no store codes**.

**Blocking gaps to raise with the customer:**
1. Full multi-store extracts of X20/X24/X70D (or the live SFTP feed) — today only 1 of 24 stores has transactional/on-hand data.
2. A store master **with SAP/store codes for all 24 stores** — needed for the store-code→warehouse crosswalk that every X-file joins on. Currently only store 14694's code is known.

Until then: products + CoA + company + warehouses (by name) can load fully; opening
stock and sales load only for store 14694.

## Prereqs
- Tenant `levis` provisioned with the `retail` industry pack (Phase 0).
- Container name below assumed `odoo19-platform-odoo-mgmt`; create `/tmp/levis` in it:
  `docker exec odoo19-platform-odoo-mgmt mkdir -p /tmp/levis`

## Go-live sequence

### 1. Company (SES) + Chart of Accounts
- **CoA** `CoA EBR.xlsx` is already clean (`code,name,account_type` with Odoo enums)
  → import via **Accounting ▸ Chart of Accounts ▸ Import**, or the Track B wizard
  (profile `levis_coa`).
- **Company** → set on the provisioned company (1 record), or Track B wizard
  (profile `levis_company`).

### 2. Products (X101) — Track A, proven (~30 min)
```
python scripts/tenants/levis/01_extract_x101.py          # HOST (openpyxl). -> out_*.csv
docker cp scripts/tenants/levis/out_categories.csv        odoo19-platform-odoo-mgmt:/tmp/levis/
docker cp scripts/tenants/levis/out_attributes.csv        odoo19-platform-odoo-mgmt:/tmp/levis/
docker cp scripts/tenants/levis/out_templates.csv         odoo19-platform-odoo-mgmt:/tmp/levis/
docker cp scripts/tenants/levis/out_template_attrlines.csv odoo19-platform-odoo-mgmt:/tmp/levis/
docker cp scripts/tenants/levis/out_variants.csv          odoo19-platform-odoo-mgmt:/tmp/levis/
docker exec -i odoo19-platform-odoo-mgmt odoo shell -d levis --no-http < scripts/tenants/levis/02_import_to_odoo.py
```
Expected: 14,885 templates · 159,658 SKUs · 170 categories · Size(89)/Inseam(24).

### 3. Stores → Warehouses (all 24)
```
python scripts/tenants/levis/03_extract_stores.py        # HOST. -> out_stores.csv (24 stores)
docker cp scripts/tenants/levis/out_stores.csv           odoo19-platform-odoo-mgmt:/tmp/levis/
docker exec -i odoo19-platform-odoo-mgmt odoo shell -d levis --no-http < scripts/tenants/levis/04_load_stores.py
```
Creates 24 warehouses keyed by name; adds `wh_<CODE>` aliases where codes are known.
**Re-run `04` after the customer supplies the missing 23 store codes** (idempotent — just adds aliases).

### 4. Opening stock (X20) — store 14694 only, until full data arrives
```
docker cp "docs/levis/X20_Current_Onhand_Inventory_Report- For current inventory.csv" odoo19-platform-odoo-mgmt:/tmp/levis/X20.csv
docker exec -i odoo19-platform-odoo-mgmt odoo shell -d levis --no-http < scripts/tenants/levis/05_load_x20.py
```
ONE-SHOT (guarded by `ir.config_parameter` marker `levis.x20_opening_stock_applied`).
Prereq: steps 2 + 3 done.

### 5. COA hygiene (demo DBs) — clean stray categories + map to EBR
The demo DBs (`demo_levis`) pick up Odoo demo-noise categories (Furniture/Office/
Outdoor/Home Construction/Non-Trade/Rental) that aren't in the EBR chart and stay
unmapped, breaking journal posting for their ~30 leftover products. Run against the
**demo** DB after seeding:
```
docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_levis --no-http < scripts/tenants/levis/32_clean_stray_categ.py
docker exec -i odoo19-platform-odoo-mgmt odoo shell -d demo_levis --no-http < scripts/tenants/levis/33_map_categ.py
```
`32` deletes the 6 stray categories (products deleted if unreferenced, else archived).
`33` is an **idempotent** safety net: maps any category still missing an income/
expense/valuation/variation/journal account to the right EBR branch (unknown roots →
`misc`). Both re-runnable; `33` no-ops once every category is complete.

## Track B (module) — Excel/CSV wizard + SFTP feed
After adding `openpyxl`+`paramiko` to `odoo/requirements.txt` and rebuilding the
image, install `custom_retail_import` on `levis`. Then:
- **Retail Import ▸ Import Data**: pick a profile (seeded for Levi's: `levis_x101`,
  `levis_coa`, `levis_company`, `levis_x20`, `levis_x24`, `levis_x70d`), upload the
  file, **Preview (dry-run)**, then **Import**. Big files run async via queue_job.
- **Configuration ▸ SFTP Feeds**: configure host/credentials + glob per file type;
  enable the `cron_poll_retail_feeds` cron for daily auto-pull (X20/X24).
- **X24 sales / X70D tenders are Phase-5 decision-gated** (POS representation, history
  depth, tax mapping) — the executor parses + groups them but refuses to post until enabled.

## Verification (in `odoo shell -d levis`)
```python
env['product.template'].search_count([])                         # ~14885
env['product.product'].search_count([('default_code','!=',False)])  # ~159658
env['account.account'].search_count([])                          # == CoA rows
env['stock.warehouse'].search_count([])                          # 24
sum(env['stock.quant'].search([]).mapped('quantity'))            # == X20 (store 14694) total
```

## Reset transactions for a re-import trial — `20_reset_txn.py`
Wipes **all transaction data** on a levis DB while **keeping master data** (CoA, taxes,
journals, products, categories, `pos.config`, payment methods + their receivable split,
partners, users, `posconfig_<store>` xids). Use it to re-run an import from a blank
ledger without re-importing the slow ~30-min X101 product master.

Wipes: `account.move`/lines/reconciles/payments/statements, POS orders/sessions/payments,
stock moves/pickings/quants, purchase/sale orders, retail-import staging (log+line), the
fixed-asset register, bank matching — **plus** the lazy X24 products (`x24prod_`) and the
`posorder_`/`posreturn_`/`x31entry_` idempotency xids.

**Always back up first** (destructive, wipes opening balances too):
```
docker exec odoo19-platform-postgres sh -lc 'PGPASSWORD=$POSTGRES_PASSWORD \
  pg_dump -h localhost -U odoo -Fc -d <db>' > /opt/odoo-platform/backups/<db>_bak_$(date +%Y%m%d).dump
```
Preview (dry-run, default) then execute:
```
docker exec -i odoo19-platform-odoo bash -lc 'RESET_DRY=1 odoo shell -d <db> --no-http' < scripts/tenants/levis/20_reset_txn.py   # closure only
docker exec -i odoo19-platform-odoo bash -lc 'RESET_DRY=0 odoo shell -d <db> --no-http' < scripts/tenants/levis/20_reset_txn.py   # execute
```
Safe by construction: it computes the transitive FK-closure of the core txn tables
**excluding** a hard GUARD of master tables, deletes with
`session_replication_role='replica'` (FK triggers off → no cascade into master), NULLs
guarded back-refs (`res_company.account_opening_move_id` etc.), and prints a master
before/after snapshot that MUST read `MASTER INTACT`. **Never** use `TRUNCATE … CASCADE`
here — it bridges via `res_company`'s opening-move FK and wipes the whole DB.

The reset does **not** touch the `retail_import.*_post_enabled` flags — set them to `0`
separately if a trial turned them on. To also drop a one-off store mapping, delete the
`posconfig_<code>` xid.

## Phase-5+ posting status (Track B)
X24 sales, X70D tenders, **X48 returns** (refund pos.orders) and **X31 discounts**
(contra-revenue reclass) now **post** behind per-file flags
`retail_import.{x24,x48,x31}_post_enabled` (+ `x24_close_sessions`), default off. GL is
period-correct (SQL re-stamp), per-tender receivable split, balanced. See memory
`x24-phase5-pos-posting` and `levis-txn-reset`.
"""
