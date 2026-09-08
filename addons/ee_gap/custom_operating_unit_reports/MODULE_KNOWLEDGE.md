---
status: reviewed
generated_at: 2026-08-11
generator: hand-written
module: custom_operating_unit_reports
manifest_version: 19.0.0.1.0
---

# custom_operating_unit_reports — Module Knowledge

## Purpose
Makes the custom accounting reports respect the reader's Operating Units.
Auto-installs where `custom_accounting_reports` and
`custom_operating_unit_docs` are both present.

## Why it is a separate module
`custom_accounting_reports` builds raw SQL over `account_move_line`, and
**`ir.rule` does not apply to raw SQL**. Without this, a scoped user's list views
are filtered and their Trial Balance is not — a leak with no symptoms.

It is a bridge rather than an edit to the reports module because that module is
installed on every accounting tenant: a schema change there would force `-u`
across all of them. The only change in the base is a no-op Python hook.

## Implementation
- `custom.report.engine._ou_sql_filter(alias)` → `(fragment, params)`:
  - unscoped reader → `("", [])`;
  - scoped, `include_untagged` on → `IS NULL OR IN %s` (same posture as the
    record rules, so history stays visible before the backfill);
  - scoped, off → `IN %s`;
  - a `report_operating_unit_ids` context filter can only **narrow** a scoped
    reader's units; anything outside them yields `AND FALSE`. Otherwise the
    wizard becomes the way around the isolation.
- `custom.report.profit.loss.branch._branch_columns()` drops columns the reader
  may not see **and the head-office column**, which is a residual absorbing every
  untagged line.
- `custom.report.journal.item.analysis.init()` wraps the base view read back from
  `pg_get_viewdef` and adds `operating_unit_id` — no copy of the base SQL, so it
  cannot drift.

## Gotchas
- **Sequence-critical**: this must be installed before any user is scoped on a
  production database.
- Adding a new report query that touches `account_move_line` means adding the
  `_ou_sql_filter` call with it. `grep -n "FROM account_move_line"` over
  `custom_accounting_reports/models/*.py` is the audit.
- The base engine flushes (`self.env.flush_all()`) before its raw SQL; the hook
  adds no flushing of its own and must not need any.

## Related
- `custom_operating_unit_docs` — the `operating_unit_id` column the filter reads.
- `custom_accounting_reports` — the hook's call sites.
