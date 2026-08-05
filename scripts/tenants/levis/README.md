# Levi's (PT Sinar Eka Selaras) — data onboarding runbook

Tenant DB: `levis`. Source files: `docs/projects/levis/`. This folder is **Track A** (ops
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

### 3b. Operating-Unit normalisation — `41_normalize_ou.py` + `42_backfill_ou_analytic.py` + `43_align_pos_naming.py`
```
RUN_DRY=0 docker exec -i -e RUN_DRY=0 odoo19-platform-odoo-mgmt odoo shell -d <db> --no-http \
    < scripts/tenants/levis/41_normalize_ou.py
RUN_DRY=0 docker exec -i -e RUN_DRY=0 odoo19-platform-odoo-mgmt odoo shell -d <db> --no-http \
    < scripts/tenants/levis/42_backfill_ou_analytic.py
RUN_DRY=0 docker exec -i -e RUN_DRY=0 odoo19-platform-odoo-mgmt odoo shell -d <db> --no-http \
    < scripts/tenants/levis/43_align_pos_naming.py
```
All three are idempotent and **dry-run by default** (`RUN_DRY=1`); run `40_setup_trade_ou.py` first,
and `43` after `41` (it reads the `pos.config` names `41` writes).

`41` leaves the "Operating Unit" analytic plan holding exactly 21 active accounts —
`EBR - HEAD OFFICE` plus the 20 live stores, all named `OLS SES - <MALL>`. Stores are
keyed by `stock.warehouse.code` (the store number the retail import joins on); codes are
never touched. The name is rewritten on the warehouse, its OU analytic, its purchase
journal (`Pembelian - <store>`) and its `pos.config`; core cascades it to the routes,
rules and stock sequences. `GRAND INDONESIA`, `PACIFIC PLACE MALL` and `PASKAL BANDUNG`
(no POS orders) are configured like live stores, then archived, as is the stray `PI021`
warehouse and the duplicate `My Company` OU.

`43` finishes the job on the POS side, which `41` does not reach: the per-store cash
journal (`Cash - <store>`), its default account when that account mirrored the journal
name, every journal's `…: Check Number Sequence`, and the already-issued documents —
`pos.session.name`, `pos.order.name` and the `ref`/`memo` fields the accounting entries
copied a session name into. It never matches on `LIKE '%OLS %'` (real product names such
as `GRAPHIC CREWNECK TEE TOOLS PEWTER` contain that substring); renames are driven by an
explicit old → new map built from `pos.config`. Chatter (`mail_message`,
`mail_tracking_value`) is left alone on purpose — it records what a record was called at
the time.

`44_fix_cash_journal_accounts.py` repairs the cash **accounts** those journals post into.
The EBR chart has no per-store cash account, so `point_of_sale` auto-created one per store
by walking the `1102` code block — and the walk collided with six genuine EBR accounts
(`Cash on hand IDR/USD/MYR/SGD`, `Cash on hand - RA`, `Cash clearing acc`), which six store
journals then adopted as their default. `Petty Cash` had the same defect. `44` gives each a
dedicated account at the next free `1102` code, reclasses the few already-posted lines off
the EBR accounts (unreconciled only, debit/credit untouched, moves stay balanced), and
archives the two unused `Cash (POS) (copy)` accounts. Run it after `43`, since the target
account name is the journal name.

The new codes differ per database (`1102000027–32` where a `Petty Cash` account already
occupied `…24`, `1102000024–29` elsewhere) — they are new accounts with no TB counterpart,
so nothing maps to them by code.

`42` stamps the OU analytic on POS revenue that was posted before
`custom_levis_localization` started doing it at source (`pos.session._get_sale_vals`).
Only `display_type='product'` lines of each `pos.session.move_id` are touched — tax,
receivable and bank lines are balance sheet. Sanity check: the analytic-ledger total must
equal the net POS income.

### 4. Opening stock (X20) — store 14694 only, until full data arrives
```
docker cp "docs/projects/levis/X20_Current_Onhand_Inventory_Report- For current inventory.csv" odoo19-platform-odoo-mgmt:/tmp/levis/X20.csv
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

### 6. EBR finance load (TB + GL) from the monthly "For Upload to Odoo" workbook
Source: `YYYY-MM - EBR - TB and GL For Upload to Odoo.xlsx` (sheets: `CoA EBR`,
`Trial Balance EBR 2026`, `GL EBR 2026`, plus subledgers). **Verified end-to-end on
`rnd_levis` — all 101 TB accounts reconcile to the sheet's June ending balances (0 diff).**

**a. Export the workbook to CSVs (HOST, needs openpyxl):**
```
python scripts/tenants/levis/59_export_ebr.py "<path>/2026-06 - EBR - TB and GL For Upload to Odoo.xlsx"
# -> ebr_coa.csv, tb_ebr.csv, gl_ebr.csv  (next to the script)
```
`59` adds a small SUPPLEMENT for accounts the TB references but the CoA sheet omits
(e.g. `1117400001` Tax Deposit).

**b. Chart of accounts** — stage `ebr_coa.csv` as `/tmp/ebr_coa.csv` and run the
existing reconciler (adds missing, preserves operational, aligns names):
```
docker cp scripts/tenants/levis/ebr_coa.csv odoo19-platform-odoo:/tmp/ebr_coa.csv
docker exec -i odoo19-platform-odoo odoo shell -d rnd_levis --no-http < scripts/tenants/levis/30_fix_coa.py
```

**c. Trial balance (summary)** — opening move (2026-01-01) + one summary movement move
per month, into a dedicated `EBRTB` journal. Idempotent; **auto-lifts and restores the
company `fiscalyear_lock_date`** (which otherwise silently bumps backdated entries to today):
```
docker cp scripts/tenants/levis/tb_ebr.csv odoo19-platform-odoo:/tmp/levis/tb_ebr.csv
docker exec -i -e TB_DRY=1 odoo19-platform-odoo odoo shell -d rnd_levis --no-http < scripts/tenants/levis/60_load_tb.py  # dry-run
docker exec -i          odoo19-platform-odoo odoo shell -d rnd_levis --no-http < scripts/tenants/levis/60_load_tb.py  # commit
```
Flags: `TB_OPENING_ONLY=1` (opening move only, then go live natively), `TB_DRY=1` (roll back).

**d. General ledger (detail)** — `61_load_gl.py` groups the GL by Document No into one
balanced `account.move` per voucher (store→analytic, business partner, journal by
Transaction Type). **BLOCKED:** the current `GL EBR 2026` sheet is *single-sided* (each
row is one leg only, no contra account, <5% have a Document No) so no voucher balances —
a `GL_DRY=1` run skips all 1461 rows. Needs a corrected **2-sided** export from the EBR/SAP
team. Fallback `GL_ALLOW_FALLBACK=1` synthesizes contra legs from `CONTRA_MAP` per
Transaction Type — **confirm the map with finance first.** Flags: `GL_DRY=1`, `GL_LIMIT=<n>`.

Reconcile after (c): `sum(debit-credit)` per account (date ≤ month-end) must equal the
sheet's Ending Balance column. Repeat the whole sequence on `prd_levis`, then `prd_detail_levis`.

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

## Purge a mis-entered PO Return — `82_purge_rtv_00005.py`
One-off correction for `prd_levis_begbal`, 05-Aug-2026: the team keyed `RTV/2026/00005`
while logged in as the shared Administrator account, then manually undid the stock with a
counter-receipt. The owner asked for full erasure rather than a cancelled trail.

Removes, in order: the two `GR-VAL`/`GR-RET-VAL` valuation entries (`force_delete` — they
are mid-chain, so a permanent `STJ/2026/08/` numbering gap is left on purpose), then the
`custom.po.return` header/lines/allocations, then the three pickings and their moves.

The stock side is done with **raw SQL, not the ORM**: `stock.move.line.unlink()` calls
`_update_reserved_quantity(-qty)` for lines whose source is an internal location, which
would drive the quant's `reserved_quantity` negative. The quants are already correct
(the return move and the counter-receipt cancel out) and must not be touched.

Hard guards on name/date/`create_uid`/amount/document ids abort on any mismatch, and the
run self-verifies that quants, the two GL account balances and `qty_received` are byte-for-byte
unchanged before committing — otherwise it rolls back. Back up first, then:
```
docker exec -i -e RTV_DRY=1 odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
    < scripts/tenants/levis/82_purge_rtv_00005.py    # report + rollback (default)
docker exec -i -e RTV_DRY=0 odoo19-platform-odoo odoo shell -d prd_levis_begbal --no-http \
    < scripts/tenants/levis/82_purge_rtv_00005.py    # execute
```
Already executed on `prd_levis_begbal`; `custom.po.return` is empty and the RTV sequence
was rolled back to `number_next = 1`.
