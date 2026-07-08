---
status: draft
generated_at: 2026-06-11T00:00:00Z
generator: claude-code
module: custom_retail_import
manifest_version: 19.0.0.1.0
---

# custom_retail_import

## Purpose
Productized adapter that converts customer-provided Excel/CSV files into Odoo records, plus an optional direct-from-SFTP recurring feed. Built for the Levi's (PT Sinar Eka Selaras / `levis` tenant) onboarding and reusable for any retail tenant. Generalizes the `custom_bank_import` template/wizard/log trio into per-file-type **import profiles**, and ports the proven `scripts/tenants/era_busana_retailindo` X101 pipeline into the X101 executor.

Answers the three customer questions: (1) Excel→Odoo adapter = the wizard + profiles; (2) read directly from FTP = `retail.import.feed` (paramiko/SFTP + cron); (3) X* master/transaction files = per-`file_type` executors.

## Business Flow
- **Manual import**: Operator opens **Retail Import ▸ Import Data** (`retail.import.wizard`), picks a `retail.import.profile`, uploads a file. `action_preview()` parses the first 20 rows and shows them with NO commit (dry-run). `action_import()` computes `sha256`, blocks duplicates (unless `force`), persists the file to `ir.attachment`, creates a `retail.import.log` (state `queued`), then runs `retail.import.executor.run(log)` — **async via queue_job** (`channel="root.retail_import"`) for large files (`ASYNC_TYPES = {x101,x20,x24,x70d,x32p}`), synchronous otherwise. Falls back to sync if queue_job is unavailable.
- **SFTP feed**: `retail.import.feed` binds an SFTP location + glob to a profile. `ir.cron cron_poll_retail_feeds` (disabled by default) → `_cron_poll_feeds()` → per active feed `_poll_one()` lists remote files matching `file_glob`, downloads each, dedups by `retail.import.log` file-hash, stores to `ir.attachment`, and enqueues the same executor.
- **Executor dispatch**: `run(log)` reads the stored attachment, calls `_load_<file_type>`. Idempotency via `ir.model.data` external IDs under `profile.namespace` (e.g. `levis`).

## Coverage by file_type (executor)
- `x101` — **FULL**. Products: builds 3-level `product.category` (CATEGORY>CLASS>SUBCLASS), `product.attribute` Size+Inseam (`create_variant=always`), `product.template` with `attribute_line_ids` (Odoo auto-generates variants), then matches auto-variants by `(template, frozenset(size,inseam value_ids))` and writes `default_code`=PROD SKU + `barcode`=PROD GTIN. Dedup by SKU keeping latest PRICE EFFECTIVE FROM. Batched commits (200 tmpl).
- `coa` — **FULL**. `account.account` from clean `code,name,account_type`; validates `account_type` against the model selection; Odoo-19 `company_ids` M2M aware (`with_company` + `(4, company.id)`).
- `company` — **FULL**. Writes `res.company` name + partner `vat`/`street`/`phone`/`email`; tolerant of the SES "Label : Value" single-cell layout.
- `x20` — **FULL**. Opening on-hand → `stock.quant` inventory adjustment per store location; resolves variant by barcode(EAN)/default_code(ITEM ID), location by `wh_<storecode>` external ID. ONE-SHOT (guarded: refuses if an `imported` log already exists for the profile).
- `x24` / `x70d` — **DECISION-GATED (Phase 5)**. Parser + transaction grouping ready (`_group_x24`); `run` raises `UserError` until POS representation, history depth, payment-method map and tax mapping are confirmed against a live DB. Target: `pos.order`/`pos.order.line` + `pos.payment`, posted **without moving stock** (X20 already set on-hand).
- `x70t` / `x31` / `x32p` / `store_master` — **STAGED**: parsed, counted, attachment kept, no model writes. X32P is reference/audit only (not replayed). Warehouse creation is done by the Track A `scripts/tenants/levis/04_load_stores.py` (Store Master stores are header-wise, not row-wise).

## Key Models
- `retail.import.profile` — Declarative parser config per file type. `read_records(file_b64, limit)` → `{records:[{logical_field: value, _row}], total_rows, blank_rows}`.
- `retail.import.log` — Audit row; `file_hash` (SHA256 dedup), `attachment_id` (kept source), `job_uuid`, `records_created/matched/skipped`, `state` ∈ queued/running/imported/partial/failed. Inherits `mail.thread`.
- `retail.import.executor` — **AbstractModel**; the per-file-type loaders. Delayable via queue_job.
- `retail.import.feed` — SFTP source (paramiko) + cron poller.
- `retail.import.wizard` (TransientModel) — Upload + preview + import.

## Important Fields
- `retail.import.profile.code` (Char, unique-per-company), `file_type` (Selection, see list), `namespace` (Char — per-tenant external-ID module, e.g. `levis`).
- `retail.import.profile.file_format` (xlsx/csv), `sheet_name`, `data_start_row` (Integer, 1-based — **the key generalization** over bank import: X70T/X31/X32P have a title row before the header; X101=3, Store Master=3, X24/X70D=2, X20=2, CoA=3).
- `retail.import.profile.column_map_json` (Text) — JSON `{logical_field: 1-based_col_index}`. Seeded per Levi's file in `data/retail_import_profiles.xml`.
- `retail.import.profile.fix_encoding` (Boolean) — restore U+FFFD → '®' (X101 quirk).
- `retail.import.log.file_hash` (Char, indexed) — dedup key.
- `retail.import.feed.password_param` (Char) — `ir.config_parameter` key holding the SFTP secret.

## Gotchas / Decisions
- **openpyxl must be in the Odoo image** for in-container `.xlsx` reading — added to `odoo/requirements.txt` (xlsxwriter in the image is write-only). `paramiko` added for SFTP. **Rebuild the image** before installing this module.
- **Large files run async** to dodge the reverse-proxy `ERR_EMPTY_RESPONSE` timeout on long synchronous web requests. The X101 import is ~30 min for ~160k variants. queue_job runner must be active (odoo-mgmt loads `queue_job` via `SERVER_WIDE_MODULES`).
- **Idempotency**: master data (products, categories, accounts) via `ir.model.data` external IDs (`noupdate=True`); transactions via file-hash + per-row external IDs; X20 opening stock is a guarded ONE-SHOT (re-applying would double on-hand).
- **SFTP credentials are stored raw** in `ir.config_parameter` — the platform has no at-rest decryptor yet (the adapter-framework `enc:` convention is aspirational). Restrict parameter read access; prefer key-based auth.
- **Data reality (Levi's, 2026-06-11)**: the delivered X20/X24/X70D are **single-store samples** (store 14694 only). X101 + CoA are full. The 24-store list comes from the Store Master (names only — no store codes for 23 of 24). The store-code→warehouse crosswalk and full multi-store transactions are blocked on the customer providing complete store-coded extracts (or the live SFTP feed). See `scripts/tenants/levis/README.md`.
- **POS history is the chosen model** for X24 (not sale.order) — register/cashier/tender/member map ~1:1 to POS. Gated on Phase-5 decisions.
- **X101 data-quality (v19.0.0.2.0)**: (1) `_clean_str` scrubs spreadsheet error sentinels (`#N/A`, `#REF!`, `#VALUE!`, …) to `""` so they no longer leak into category names/SKUs/barcodes (a real category literally named `#N/A` was observed — openpyxl `data_only=True` returns cached VLOOKUP errors as strings). (2) X101 merchandise is created **storable** (`is_storable=True`, type `consu`); the **"Original cut" tailoring service** → `type="service"`, detected by `ir.config_parameter` `retail_import.service_product_codes` (exact code) or `retail_import.service_category_keywords` (substring). **Both default EMPTY** — a substring default like `TAILOR` false-matched 102 real merchandise rows in rnd_levis ("TAILORED BUSTIER", "TAILORED CLASSIC" shirts), so everything is storable merchandise until the actual service marker is configured. (3) Rows with a **blank category** or **zero/unparseable price** are flagged `state=error` on `retail.import.line` (bumps `error_count` → log state `partial`) but still imported (no silent data loss). Remediate already-imported DBs with `scripts/tenants/levis/71_fix_retail_import_dataquality.py` (dry-run default; `RETAIL_FIX_APPLY=1` to write).
- **Storable ⇒ POS must still not move stock**: making merchandise storable means POS session-close would otherwise create pickings (Odoo gates this on `pos.session.update_stock_at_closing`, derived from company config). The X24/X48 executors force `update_stock_at_closing=False` on import-created sessions (post-create, since `pos.session.create` overrides it) so the financial-only replay never double-counts the X20 on-hand snapshot. The `:1002` guard (`UNEXPECTED n stock move(s) on close`) is the tripwire.

## Related
- `scripts/tenants/levis/` — Track A ops scripts (fast go-live without the image rebuild): `01_extract_x101.py`+`02_import_to_odoo.py` (products), `03_extract_stores.py`+`04_load_stores.py` (warehouses), `05_load_x20.py` (opening stock).
- `scripts/tenants/era_busana_retailindo/` — the original precedent this module generalizes.
- `addons/ee_gap/custom_bank_import/` — the template/wizard/log pattern this extends.
- `addons/core/custom_adapter_framework/` — adapter config/credential pattern (SFTP alternative).
