---
status: draft
generated_at: 2026-07-02T07:43:22Z
generator: bootstrap-v1
module: custom_accounting_reports
manifest_version: 19.0.0.22.0
---

# custom_accounting_reports

## Purpose
This module closes the Enterprise gap on Odoo CE `account_reports`. It provides a comprehensive suite of financial reports for the Custom Platform — P&L, Balance Sheet, Cash Flow (indirect method), General Ledger, Trial Balance, Partner Ledger, Partner Cards, Aged Receivable/Payable, Tax (PPN/PPh), Day/Cash/Bank Book, Journal Audit, Down-Payment (Uang Muka) ledger, Sales, and a tree-driven custom Financial Report. All reports are built on a single shared `custom.report.engine` AbstractModel and render to QWeb PDF/HTML or XLSX.

## Business Flow
1. **User Selection**: The user opens a report from the menu (e.g., Trial Balance, General Ledger).
2. **Wizard Input**: A transient wizard (`custom.report.*.wizard`, under `wizard/`) collects filters such as date range, companies, journals, accounts, partners, and posted-only.
3. **Report Generation**: The wizard normalises its fields into a `filters`/`options` dict and hands off to the matching report model, which runs parameterised SQL against `account_move_line` via the engine helpers and builds report lines.
4. **Export/View**: Output is rendered as a QWeb PDF/HTML report (via the shared dispatch model) or exported to XLSX. Each run is written to the `pdp.audit_log` audit trail.

## Key Models
All report models are `AbstractModel`s that inherit `custom.report.engine` (the architectural base), except the concrete `custom.report.financial` tree and the QWeb dispatch model.

- `custom.report.engine` — **AbstractModel base.** Filter normalisation, raw-SQL aggregation (`_get_account_balances`, `_get_move_lines_query`, `_sum_by_account`), XLSX export, render context, and PDP audit logging.
- `report.custom_accounting_reports.report_dispatch` — **AbstractModel.** QWeb report dispatcher; maps a `report_code` to the target report model and returns its computed context.
- `custom.report.general.ledger` — General Ledger.
- `custom.report.trial.balance` — Trial Balance (default dispatch target).
- `custom.report.profit.loss` — Profit & Loss, bucketed by `account.group` (GROUP 1 code prefix), falling back to `account_type`.
- `custom.report.profit.loss.branch` — Profit & Loss with one amount column per branch; inherits `custom.report.profit.loss`. Reached from the P&L wizard's *View / Export by Branch* buttons (it owns no wizard, so no tenant needs a schema upgrade).
- `custom.report.balance.sheet` — Balance Sheet (Asset / Liability / Equity by account type, nested by `account.group`), including a computed **Current Year Earnings** equity line.
- `custom.report.cash.flow` — Cash Flow Statement (indirect method).
- `custom.report.partner.ledger` — Partner Ledger.
- `custom.report.partner.card.base` — Partner card base, subclassed by `custom.report.payable.card` and `custom.report.receivable.card`.
- `custom.report.aged.receivable` — Aged Receivable; `custom.report.aged.payable` inherits it.
- `custom.report.ar.aging.export` — AR Aging Export. Inherits `custom.report.aged.receivable` for its open-line query, but replaces the layout: one **flat** row per open receivable line carrying the commercial trail (customer PO / SO / DO), the tax split (DPP / PPN / Full), the settlement figures (Original / Paid / Outstanding) and fifteen *overdue-day* buckets (`<= 0`, then 1…7 day by day, `8-14`, `15-30`, `31-60`, `61-90`, `91-120`, `121-360`, `> 360`). Reached from the **AR Aging Export** menu, which opens the Aged Receivable wizard with `ar_aging_export` in the context.
- `custom.report.advance` — Uang Muka / Down-Payment ledger (auto-detects advance accounts).
- `custom.report.sales` — Sales report.
- `custom.report.tax` — Tax report (PPN / PPh subtotals; cross-references Coretax).
- `custom.report.ppn.digunggung` — **Rekap PPN Keluaran Digunggung (PKP Pedagang Eceran).** Output VAT riding on **non-invoice** moves (POS journal entries), which is what a retail tenant actually has: `custom.report.faktur.pajak` and the FK/OF export are both keyed on `out_invoice` and show nothing. Emits a per-masa recap (the SPT 1111 figure) followed by a per-day, per-Operating-Unit detail. Presents an 11% tax PMK 131-style — statutory 12% on a DPP Nilai Lain of 11/12 — matching `custom_coretax_export`'s FK rows; the PPN rupiah is unchanged so it still ties to the GL.
- `custom.report.book.mixin` — Day/Cash/Bank book mixin, subclassed by `custom.report.day.book`, `custom.report.cash.book`, `custom.report.bank.book` (three distinct models).
- `custom.report.journal.audit` — Journal Audit.
- `custom.report.financial` — **Concrete `models.Model`.** The only ORM model with stored fields; a self-referential tree defining custom financial-report line structure. Rendered by the `custom.report.financial.renderer` AbstractModel.

## Important Fields
Report models are AbstractModels and generally have no stored fields; user input lives on the transient wizards under `wizard/`.

- **custom.report.financial** (the only model with fields)
  - `parent_id` / `child_ids`: self-referential tree (`custom.report.financial`).
  - `account_ids`: `Many2many` to `account.account`.
  - `company_id`: `Many2one` to `res.company`.
  - `code`, `name`: used to compute the display name `[code] name`.

- **custom.report.advance.wizard**
  - `account_ids`: `Many2many` to `account.account`.
  - `company_ids`: `Many2many` to `res.company`.
  - `date_from`, `date_to`: report date range.
  - `posted_only`: `Boolean` (default `True`).

- **custom.report.aged.receivable.wizard / aged.payable.wizard**
  - `partner_ids`: `Many2many` to `res.partner`.
  - `detail_mode`: `Selection` switching summary vs. detail layout, **defaulting to `detail`**. (Note: `aging_detail` is only a **context key** derived from `detail_mode == "detail"`, not a field.)

- **Cash Flow bucketing** — `custom.report.cash.flow` has no `account_type` field. Buckets are defined by module-level tuples `OPERATING_TYPES`, `INVESTING_TYPES`, `FINANCING_TYPES`, `CASH_TYPES` matched against each row's Odoo `account_type`.

## Public Methods
- **Wizards** (entry points, e.g. `custom.report.advance.wizard`)
  - `action_print()`: renders the report to QWeb PDF/HTML.
  - `action_export_xlsx()`: exports to XLSX.

- **custom.report.engine** (shared, inherited by all report models)
  - `_default_filters()` / filter normalisation.
  - `_get_account_balances(filters)`, `_get_move_lines_query(...)`, `_sum_by_account(...)`: raw-SQL aggregation helpers.
  - `_compute(options)`: builds the render context.
  - `_account_groups(account_ids)`: two-level `account.group` ancestry per account; `{}` when the database defines no groups (the signal to fall back to `account_type`).
  - `_grouped_section(label, rows)`: nests signed rows under their GROUP 2 headers; degrades to a flat `accounts` list without groups.
  - `_branch_plan()`: the `account.analytic.plan` carrying the branch dimension, named by the `custom_accounting_reports.branch_plan_name` config parameter (default `Operating Unit`).
  - `_log_report_run(...)`: writes a run record to `pdp.audit_log`.
  - `get_report_table(options, context_extra)`: payload for the `custom_report_table` OWL client action — `columns` from `_xlsx_columns()` plus display `lines` from `_flatten_for_screen()`.
  - `_flatten_for_screen(lines, columns)` / `_screen_row(...)`: turn `_build_lines()` output into flat display rows. The default passes rows straight through, which suits reports whose lines are already flat.
  - `_flatten_grouped(lines, columns, group_type, heading, totals, total_label=None, opening_field=None)`: the flattener for reports that nest their movements under a group row. Mirrors their `_xlsx_body`: group heading (with the opening figure), the movements, the group total, then the grand total.

- **Report models**
  - `_build_lines(filters)`: overridden per report to build its lines (e.g. `custom.report.aged.receivable._build_lines`).
  - `_xlsx_body(sheet, ctx, columns, fmts, start_row)`: writes the Excel sheet; the grouped reports walk their nested lines here by hand.
  - `_flatten_for_screen(...)`: overridden by `custom.report.general.ledger` (grouped layout only), `custom.report.partner.ledger` and `custom.report.advance` to delegate to `_flatten_grouped`.
  - `custom.report.cash.flow._bucket(label, code, type_codes, balances, sign=-1)`: computes an activity bucket.

## Integration Points
- **Depends on**: `custom_core`, `custom_pdp_audit`, `custom_accounting_full`, `account`
- **Architecture**: every report is an AbstractModel inheriting the shared `custom.report.engine`; only `custom.report.financial` is a concrete ORM model. No `account.move` inheritance.
- **External calls**: `_log_report_run` executes a raw SQL `INSERT INTO pdp.audit_log` on every report run (via `self.env.cr.execute`).
- **Wizards**: live under `wizard/` (singular). There is no `controllers/` directory.

## Gotchas
- **The reports build raw SQL, so `ir.rule` does not apply to them.** Every query
  that touches `account_move_line` must splice in `_ou_sql_filter(alias)` — a
  no-op here, implemented by `custom_operating_unit_reports`. Miss it on a new
  query and a store-scoped user reads other branches' numbers while their list
  views look correctly filtered: a leak with no symptoms. Call sites today:
  `_get_move_lines_query`, `_sum_by_account`,
  `custom_report_general_ledger`, `custom_report_profit_loss_branch._sum_by_account_and_branch`.
- All computation runs through the single `custom.report.engine` base; overriding `_build_lines` is the extension point, not adding fields.
- **Output VAT is split across exactly two reports, by buyer identity.** Invoiced sales (`out_invoice`/`out_refund`) belong to `custom.report.faktur.pajak` + the FK export; everything else — retail, buyer not identified — belongs to `custom.report.ppn.digunggung`, whose domain excludes those two move types on purpose. Widen either side and the masa is double-counted; narrow both and PPN disappears from the working papers with the GL still balanced.
- **Never bucket a P&L by `account_type` alone.** Indonesian charts type every cost-of-sales account plain `expense` (not `expense_direct_cost`), so a type-based split reports COGS as zero, files `income_other` under Revenue, and drops `expense_other` entirely. Section membership comes from the account-code prefix via `account.group`.
- `account.account.group_id` is **computed, not stored** in Odoo 19 (resolved from the code prefix). It cannot appear in a SQL join or an ORM domain — read it off a browsed recordset, as `_account_groups` does.
- `account.group` rows are company-scoped; `account.analytic.plan` is not, but its accounts are. Both are filtered against the active companies.
- This module ships to every tenant. Adding a field or a `TransientModel` forces an `-u` on **all** databases that have it installed, or their General Ledger wizard breaks and their autovacuum cron logs errors. Prefer context keys and buttons on existing wizards.
- **A report that nests its movements under a group row must override `_flatten_for_screen`.** `_xlsx_columns()` + `_build_lines()` feed both Excel and the screen, but `_xlsx_body` walks the nesting itself while the default flattener does not — so the export looks right while the on-screen table shows one blank row per group and no movements. Delegate to `_flatten_grouped` (GL grouped layout, Partner Ledger, Advance do).
- Inside those flatteners, use `self.env._("fmt %s", arg)` — the module-level `_()` sniffs the caller frame for a language and logs a warning with a full stack trace **per row** when called from a lambda.
- The `custom.report.advance` model auto-detects advance/down-payment accounts by name, which may not cover all chart-of-account edge cases.
- `custom.report.aged.payable` inherits `custom.report.aged.receivable`, reusing its layout logic.
- **`custom.report.ar.aging.export` inherits the aged-AR report but must NOT inherit its layout hooks.** It reuses `_open_lines` / `_account_type` only; `_build_lines`, `_flatten_for_screen`, `_classify_bucket` and `_xlsx_body` are all replaced, because the parent's versions walk a partner-grouped bucket matrix this report does not build. In particular `_flatten_for_screen` restores the *engine's* pass-through flattener by hand — calling `super()` there yields blank rows.
- **The AR Aging Export ships no wizard of its own.** It drives `custom.report.aged.receivable.wizard` through the `ar_aging_export` context key set by its menu action, which swaps the footer buttons (`action_view_ar_aging` / `action_print_ar_aging` / `action_export_ar_aging_xlsx`) and hides `detail_mode`. That is deliberate: a new `TransientModel` would force an `-u` on every tenant that has this addon installed.
- The AR Aging Export **PDF deliberately drops the 15 bucket columns** (34 columns is unreadable on paper) and prints the document trail + amount summary + overdue day count instead. The Excel export and the on-screen table carry the full grid.
- Its `Tax No` column reads `x_custom_nsfp` through `_opt`, so it stays blank rather than crashing on tenants without `custom_coretax`; `No. SO` / `No. DO` degrade the same way when `sale` / `stock` are absent.
- Every run performs a defensive raw-SQL insert into `pdp.audit_log`; failures are logged as warnings and do not block the report.
- **A hook that sets `active` on a data-file record needs `noupdate="1"` to survive.** The XStore menu was archived by `hooks.sync_pos_only_menus`, then silently un-archived by the next `-u`, because loading `menu_views.xml` rewrites a plain menuitem. It bit prd_arkaaim and trn_arkaaim on the 0.16.0 → 0.17.0 upgrade. The menuitem now sits in its own `<data noupdate="1">` block — the cost is that renaming or re-sequencing it takes a migration script. The same trap applies to any record whose runtime state a hook owns.
- **`AR Aging Export` is a second aging report on purpose, not a duplicate.** `custom.report.aged.receivable` answers "how old is my AR" in seven wide buckets; `custom.report.ar.aging.export` (which inherits it) is Finance's per-document collection worklist — one row per open receivable line with the commercial trail (customer PO / SO / DO), the DPP/PPN split, original/paid/outstanding, and **fifteen** overdue buckets whose edges come from Finance's own workbook (day-by-day for the first week, then widening). Do not "simplify" the two into one.
- **It reuses the Aged Receivable wizard rather than shipping its own.** This addon is installed on every tenant, so a new `TransientModel` would force an `-u` across all of them. The menu points at the same wizard with `{'ar_aging_export': 1}` in the context, and the view swaps the buttons on that key. Its `date_from` is pinned to 1970 — an aging worklist is as-of-a-date, not a period.
- **The Purchase Register splits Trade / Non-Trade defensively.** `account.move.l10n_purchase_type` is added by the tenant module `custom_levis_localization`, which this addon must not depend on, so `custom.report.purchase._purchase_type_available()` gates the `Type` column, the `purchase_type` wizard filter (hidden through the non-stored `show_purchase_type` compute) and the `By Trade / Non-Trade` grouping. On a tenant without the field the report renders exactly as before. Blank streams are resolved from the reversed entry, then the source PO line, before being reported as `Unclassified` — credit notes created with "Reverse" carry no stream of their own.
- **A new report code must be registered in TWO places.** `REPORT_MODEL_MAP` in `models/custom_report_dispatch.py` *and* the `t-elif` chain in `reports/report_common.xml`. Miss the first and the code silently falls back to Trial Balance; miss the second and the PDF renders empty.
- **`Sales Detail (XStore X24DN)` is archived on tenants without POS.** It reads `pos.order.line` and the `ri_src_*` columns `custom_retail_import_pos` adds, so on ARKA-AIM — which runs the importer without `point_of_sale` on purpose — it could only ever render empty. The menu cannot be gated declaratively (`groups="point_of_sale...."` would need a dependency this module must not have), so `hooks.sync_pos_only_menus` resolves `active` at install/upgrade, and `custom_retail_import_pos`'s own `post_init_hook` re-shows it if POS arrives later. Add any further POS-only menu to `hooks.POS_ONLY_MENUS`.
- **This module's groups sit on its own `custom_accounting_reports.res_groups_privilege_accounting_reports` privilege** ("Accounting Reports") — Odoo 19 renders every group sharing one `res.groups.privilege` as a single pick-one dropdown on the user form, so a privilege shared across modules makes saving a user silently drop the other modules' groups. The privilege carries `custom_core.module_category_custom_platform`, so the selector still appears alongside the other custom modules. Do not point new groups at `custom_core.res_groups_privilege_custom_platform`.

## Out of Scope
- No real-time reporting or live data updates; reports are computed on demand from posted/existing move lines.
- No direct integration with external tax-filing systems (the tax report only cross-references Coretax data).
