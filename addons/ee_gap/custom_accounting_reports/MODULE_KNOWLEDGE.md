---
status: draft
generated_at: 2026-05-21T00:00:00Z
generator: claude-code-bootstrap-v1
module: custom_accounting_reports
manifest_version: 19.0.0.1.0
---

# custom_accounting_reports

## Purpose
Closes the EE `account_reports` gap. Provides 14 dynamic financial reports built atop a single shared `custom.report.engine` AbstractModel: Profit & Loss, Balance Sheet, Cash Flow (indirect), General Ledger, Trial Balance, Partner Ledger, Aged Receivable, Aged Payable, Tax Report (PPN/PPh subtotals; cross-refs Coretax), Day Book, Cash Book, Bank Book, Journal Audit, and a tree-driven custom Financial Report (`custom.report.financial`).

Every report is wizard-driven, dispatched through a single `report.custom_accounting_reports.report_dispatch` AbstractModel, runs parameterised raw SQL (never string-concatenated) against `account_move_line`, and writes a PDP audit row per execution. Default PSAK-aligned financial tree shipped in `data/financial_report_seed_psak.xml`.

## Business Flow
- User opens a wizard (e.g. `general.ledger.wizard`) and fills `date_from`, `date_to`, `company_ids`, optional `journal_ids`/`account_ids`/`partner_ids`, `posted_only`, and optional `comparison` flag.
- Wizard's `action_print()` / `action_view()` triggers `ir.actions.report` with `report_name='custom_accounting_reports.report_dispatch'` and a `data` dict carrying `report_code`, `options`/`filters`, optionally `doc_model`/`docids`.
- `CustomReportDispatch._get_report_values(docids, data)` reads `data['report_code']`, looks up the concrete sub-report model in `REPORT_MODEL_MAP` (e.g. `general_ledger → custom.report.general.ledger`), and calls `report._compute(filters)`.
- `CustomReportEngine._compute(filters)` normalises filters via `_get_context_filters`, calls subclass `_build_lines(filters)`, writes a PDP audit row via `_log_report_run`, and returns a context dict (`report_code`, `report_title`, `filters`, `lines`, `currency`, `company_names`, formatted date strings).
- Subclass `_build_lines(filters)` typically calls `self._get_account_balances(filters)` (parameterised SQL aggregation on `account_move_line`) and shapes rows for the QWeb template.
- Output rendered via `reports/<report>_template.xml` QWeb templates; `reports/report_common.xml` provides shared header (`_coverage_banner`).
- Custom Financial tree: `custom.report.financial` is a `_parent_store` recursive tree with `type` ∈ accounts/account_type/tags/computed, `sign` (+1/-1), `style` (normal/header/subtotal/total). `custom.report.financial.renderer._build_lines` walks the tree via `_node_value` (memoised against `balance_cache` + `type_cache`) and flattens via `_flatten`.

## Key Models
- `custom.report.engine` — `AbstractModel`; base for every concrete report. Owns filter normalisation + SQL aggregation + render context + PDP audit hook.
- `custom.report.dispatch` (technical `report.custom_accounting_reports.report_dispatch`) — `AbstractModel`; routes `report_code` → concrete report model via `REPORT_MODEL_MAP`.
- `custom.report.general.ledger` / `custom.report.trial.balance` / `custom.report.balance.sheet` / `custom.report.profit.loss` / `custom.report.cash.flow` / `custom.report.aged.receivable` / `custom.report.aged.payable` / `custom.report.partner.ledger` / `custom.report.tax` / `custom.report.day.book` / `custom.report.cash.book` / `custom.report.bank.book` / `custom.report.journal.audit` — concrete `AbstractModel`s, each setting `_report_code` + `_report_title` and overriding `_build_lines`.
- `custom.report.financial` — Persistent (non-abstract) hierarchical tree node (`_parent_store=True`, `parent_id`/`children_ids`); the editable definition.
- `custom.report.financial.renderer` — `AbstractModel` extending engine; renders any `custom.report.financial` tree.
- Wizards (one per report): `general.ledger.wizard`, `trial.balance.wizard`, `balance.sheet.wizard`, `profit.loss.wizard`, `cash.flow.wizard`, `aged.receivable.wizard`, `aged.payable.wizard`, `partner.ledger.wizard`, `tax.report.wizard`, `day.book.wizard` — `TransientModel`s capturing filters.

## Important Fields
- `custom.report.engine._report_code` (class attr, str) — stable identifier matching `REPORT_MODEL_MAP` keys.
- `custom.report.engine._report_title` (class attr, str) — display title.
- `custom.report.engine` filter envelope (dict, not stored): `date_from`, `date_to`, `company_ids`, `journal_ids`, `account_ids`, `partner_ids`, `posted_only` (default True), `comparison` (bool), `comparison_date_from`, `comparison_date_to`.
- `custom.report.financial.category` (Selection balance_sheet/profit_loss/cash_flow/custom) — top-level grouping; children inherit.
- `custom.report.financial.type` (Selection accounts/account_type/tags/computed) — aggregation mode; `computed` = sum of children.
- `custom.report.financial.sign` (Integer, default 1) — flip sign for natural-positive presentation (e.g. -1 on revenue).
- `custom.report.financial.style` (Selection normal/header/subtotal/total) — QWeb styling hint.
- `custom.report.financial.account_ids` (M2m `account.account`) — explicit account list when `type='accounts'`.
- `custom.report.financial.account_type_ids` (Char) — comma-separated list of `account.account.account_type` values when `type='account_type'`.
- `custom.report.financial.code` (Char, required) — stable identifier for XML data linking.
- `custom.report.financial.parent_id` / `parent_path` / `children_ids` — tree structure.

## Public Methods
- `custom.report.engine._compute(filters=None)` — public entry; returns render context dict.
- `custom.report.engine._build_lines(filters)` — abstract hook each subclass overrides.
- `custom.report.engine._default_filters()` / `_get_query_filters(wizard)` / `_get_context_filters(filters)` — filter pipeline.
- `custom.report.engine._get_account_balances(date_from=None, date_to=None, company_ids=None, journal_ids=None, *, filters=None)` — three call shapes (dict-as-positional, positional, kw).
- `custom.report.engine._sum_by_account(filters, account_domain=None)` — raw-SQL per-account aggregation; hot path for TB/GL/BS.
- `custom.report.engine._get_move_lines_query(filters)` — returns `(query, params)` for raw per-line iteration.
- `custom.report.engine._base_move_line_domain(filters)` — ORM-domain equivalent for non-SQL paths.
- `custom.report.engine._log_report_run(filters)` — direct INSERT into `pdp.audit_log` (best-effort, swallows exceptions).
- `custom.report.engine._format_amount(value, currency=None)` / `_format_date_id(value)` (Indonesian dd/mm/yyyy) / `_coverage_banner(filters)`.
- `custom.report.dispatch._get_report_values(docids, data=None)` — Odoo `ir.actions.report` dispatch entry.
- `custom.report.financial._node_value(balance_cache, type_cache)` — recursive signed aggregation.
- `custom.report.financial._flatten(balance_cache, type_cache, lines, depth=0)` — produces line dicts for QWeb.
- `custom.report.financial.get_account_type_codes()` — splits CSV `account_type_ids` into list.

## Integration Points
- **Depends on:** `custom_core`, `custom_pdp_audit`, `custom_accounting_full`, `account`.
- **Inherits from:** `account.account` / `account.move.line` queried only — no model inheritance.
- **Extended by:** `custom_accounting_full` ships the data the reports consume; downstream verticals add report variants by subclassing `custom.report.engine`.
- **External calls:** none.
- **Cross-vertical:** generic.
- **Coretax cross-ref:** Tax Report (`custom.report.tax`) cross-references `custom_coretax` PPN data — the report module does not depend on Coretax but renders empty subsections when Coretax isn't installed.

## Gotchas
- **`_get_account_balances` has three call shapes** — `(filters_dict)`, `(date_from, date_to, company_ids, journal_ids)`, `(filters=filters_dict)`. The auto-detect `if isinstance(date_from, dict)` branch is fragile; never pass a real `date` for `date_from` when you intend the dict shape.
- **Filters fall back to `[self.env.company.id]`** when `company_ids` is empty — `IN ()` SQL would crash; this defensive default may silently scope a report to a single company.
- **`posted_only` defaults True everywhere**; setting it False includes drafts AND the `parent_state IN ('draft','posted')` filter widens both SQL and ORM paths.
- **`_log_report_run` swallows ALL exceptions** including a missing `pdp.audit_log` table — audit absence is invisible.
- **`custom.report.financial.account_type_ids` is a comma-separated Char**, not a M2m — typos won't validate; `get_account_type_codes` returns whatever's there.
- **`custom.report.financial._check_recursion`** is named the same as a base helper — the inner check is `if not self._check_recursion(): raise` (calls base then negates); a true cycle would already have been blocked, the explicit constraint is partially redundant.
- **Date-from > date-to is silently swapped** in `_get_context_filters` — caller never knows.
- **Comparison-period auto-derivation** uses `(date_to - date_from).days + 1` span; not calendar-aware (Jan vs Feb day counts).
- **PSAK seed in `data/financial_report_seed_psak.xml`** is the canonical default tree — overriding requires editing data or runtime config; no per-tenant variant mechanism.
- **No XLSX export** in-tree — output is QWeb PDF/HTML only; verticals must add an XLSX renderer if needed.
- **Tax Report depends on cross-module data** but does not declare `custom_coretax` in `depends` — installing without Coretax leaves PPN columns empty without warning.

## Out of Scope
- **Live editing of report definitions from UI** — `custom.report.financial` is editable but other reports (P&L, BS, Cash Flow renderers) are code-defined.
- **Drill-down** — outputs are static; no interactive expand-collapse beyond the QWeb tree.
- **Currency conversion to a presentation currency** — `currency` in the render context is the first `company_ids` company's currency.
- **XBRL / iXBRL export** — only PDF/HTML.
- **Saved report definitions per user** — wizard transient only.
