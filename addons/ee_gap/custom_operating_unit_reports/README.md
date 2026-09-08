# Custom Operating Unit — Reports

Makes the custom accounting reports respect the reader's Operating Units.

## Why this module exists separately

`custom_accounting_reports` builds its own SQL over `account_move_line` for
speed, and **`ir.rule` does not apply to raw SQL**. Without this bridge, a
store-scoped user sees their own store in every list view and *every* store in
a Trial Balance, a General Ledger or a P&L. Nothing looks broken — which is what
makes it the worst kind of leak.

The base module gains only one thing, a pure-Python no-op hook
(`custom.report.engine._ou_sql_filter`) spliced into each ledger query. This
module implements it. **When you add a report query that touches
`account_move_line`, splice the hook in with it.**

## What it does

* Restricts `_get_move_lines_query`, `_sum_by_account`, the General Ledger and
  the P&L-by-branch to the reader's units, with the same posture as the record
  rules (untagged rows stay visible while `include_untagged` is on).
* Drops the head-office **residual** column from the P&L by branch for a scoped
  reader — it absorbs every untagged line, so leaving it in would hand a store
  user the company's remainder.
* An explicit `report_operating_unit_ids` context filter can only *narrow* a
  scoped reader's units, never widen them.
* Adds `operating_unit_id` to the GL Analysis cube, by wrapping the base view
  read back from Postgres rather than copying its SQL.

Auto-installs where the reports and `custom_operating_unit_docs` both are.

**Sequence-critical: install this before assigning Operating Units to anyone on
a production database.**
