# Enterprise Accounting Gap Audit — Juli 2026

Audit menu/fitur **Odoo 19 Enterprise Accounting** vs modul yang sudah dimiliki
odoo-platform (Community 19 + addons `ee_gap`). Diverifikasi terhadap core CE 19
di container runtime (`/usr/lib/python3/dist-packages/odoo/addons/account`) dan
DB `prd_levis_begbal`.

## 1. Coverage — modul platform vs fitur EE

| Fitur EE Accounting | Modul platform | Menu | Status |
|---|---|---|---|
| Financial reports (P&L, BS, GL, TB, Cash Flow, Aged, Partner Ledger, dst) | `custom_accounting_reports` | Reporting → 14+ laporan + Laporan Pajak (PPN/PPh/SPT/Bupot/Ekualisasi) | ✅ |
| Consolidation | `custom_accounting_full` | Group Reporting (perimeters, elimination rules/proposals, TB/P&L/BS konsolidasi) | ✅ |
| Payment follow-ups / dunning | `custom_accounting_full` | Customer Follow-up + levels + credit-check logs | ✅ |
| 3-way match | `custom_accounting_full` | 3-Way Match Policy / Results | ✅ |
| Fixed assets & depreciation | `custom_accounting_asset` | Assets (register, post depreciation, revaluation, disposal) | ✅ (straight-line saja) |
| Recurring entries | `custom_accounting_recurring` | Recurring → JE & payment templates | ✅ |
| Fiscal-year closing | `custom_accounting_full` | Fiscal Years + close wizard | ✅ |
| EDI / e-invoicing | `custom_coretax*` + `custom_tax_id` | Coretax export, Pajakku H2H, withholding | ✅ (lokal Indonesia) |
| Manual reconciliation | `custom_account_reconcile` (Jul 2026) | Accounting → Reconciliation → Reconcile | ✅ |
| Bank statement import / feeds | `custom_bank_import` | Bank Import (CSV/XLSX per-bank + H2H API) | ✅ (file+H2H; tanpa agregator Plaid/SaltEdge — N/A ID) |
| Expense OCR | `custom_expenses` | Expenses (AI/Approval) | ✅ (struk expense saja) |
| Budget | `custom_finance_budget` | Finance Budget | ⚠️ khusus SAP-sync, bukan budget analitik umum |
| Documents / Sign / Spreadsheet | `custom_documents` / `custom_sign` / `custom_spreadsheet` | masing-masing | ✅ |
| Petty cash (tidak ada di EE, bonus) | `custom_petty_cash` | Petty Cash | ✅ |

## 2. Sudah ada di core CE 19 — BUKAN gap

| Fitur | Bukti |
|---|---|
| Lock dates (fiscalyear + hard lock) | `res.company` core |
| Inalterability hash / secured entries | `account.move.inalterable_hash`, wizard `account_secure_entries_wizard` |
| Multi-Ledger / journal groups | menu core `menu_action_account_journal_group_list` |
| Reconcile models (config) | `account.reconcile.model` (config-only; matcher-nya EE) |
| Partial reconcile + matching numbers | `account.move.line.reconcile()` |
| Auto-post entri berjangka | `account.move.auto_post` + cron `_autopost_draft_entries` |

## 3. Gap riil (per Juli 2026)

| # | Fitur EE | Status | Tindak lanjut |
|---|---|---|---|
| 1 | Deferred revenue/expense (spread otomatis) | ❌ (file `deferred_wizards_views.xml` di custom_accounting_reports ternyata wizard PPh — salah nama) | **Dibangun: `custom_account_deferred`** |
| 2 | Bank reconciliation widget (statement-line ↔ AML matching) | ⚠️ parsial (manual matching saja) | **Dibangun: extend `custom_account_reconcile` v2** |
| 3 | Batch payments + payment file export bank | ❌ | **Dibangun: `custom_account_batch_payment`** |
| 4 | Vendor-bill OCR (`account_invoice_extract`) | ❌ (hanya OCR struk expense) | Backlog |
| 5 | Margin analysis | ❌ | Backlog |
| 6 | Disallowed expenses (koreksi fiskal) | ❌ | Backlog (relevan utk ekualisasi pajak ID) |
| 7 | Online bank feeds (Plaid/SaltEdge/Yodlee) | ❌ | N/A Indonesia — H2H `custom_bank_import` menggantikan |
| 8 | Intrastat / SEPA | ❌ | N/A Indonesia |
| 9 | Budget analitik EE | ⚠️ | Backlog bila dibutuhkan di luar use-case SAP |

## 4. Temuan sampingan

- `custom_bank_import/models/bank_import_template.py` masih memakai
  `_sql_constraints` — **diabaikan diam-diam oleh Odoo 19** (harus
  `models.Constraint`). Bug laten, perlu follow-up.
- `custom_accounting_reports/wizard/deferred_wizards_views.xml` sebaiknya
  di-rename (isinya wizard PPh reconciliation/PPh 25).
