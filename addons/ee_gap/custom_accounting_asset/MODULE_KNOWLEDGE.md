---
status: draft
generated_at: 2026-07-02T07:18:43Z
generator: bootstrap-v1
module: custom_accounting_asset
manifest_version: 19.0.0.1.0
---

# custom_accounting_asset

## Purpose
Closes the EE `account_asset` gap for Odoo CE: a fixed asset register with a monthly depreciation schedule, automatic GL posting of due depreciation, a disposal workflow that books a balanced journal entry, and an XLSX/PDF asset register report ("Daftar Aktiva Tetap & Penyusutan").

## Business Flow
1. **Asset Creation**: Users create fixed assets (`custom.fixed.asset`), optionally assigning a group (which supplies default useful life and accounts) and a hierarchical location. `code` is auto-assigned from the `custom.fixed.asset` sequence.
2. **Confirmation & Schedule Generation**: `action_confirm` validates that expense/accumulated accounts and a journal are set (unless method = `none`), calls `_build_schedule()` to generate depreciation lines from the selected method (straight line or declining balance) and useful life, then moves the asset to `running`. Already-posted lines are preserved; only unposted lines are rebuilt.
3. **Automatic Posting**: `_post_due_depreciation` posts all unposted lines whose date is on/before a cut-off, creating one `account.move` per line (DR expense / CR accumulated depreciation) and marking the line `posted`. `_cron_post_due_depreciation` is the cron entry point that runs this over every running asset.
4. **Manual Posting Override**: On a depreciation line, `action_post_now()` (on `custom.fixed.asset.depreciation.line`) posts a single line ahead of the cron schedule via `_post_due_depreciation(as_of=line.date)`.
5. **Disposal Management**: `action_open_dispose_wizard` opens the disposal wizard; `action_dispose` optionally builds a balanced disposal `account.move` (release accumulated depreciation, book proceeds, record gain/loss, release asset cost) and writes the asset to `disposed`.
6. **Report Generation**: The asset register wizard prints a PDF or exports XLSX per year, one row per asset with acquisition value, opening accumulated depreciation, Jan–Dec monthly amounts, YTD, year-end accumulated depreciation, and book value.

## Key Models
- `custom.fixed.asset` — Individual fixed assets; acquisition data, account overrides, depreciation schedule, state machine, and disposal fields. (`fixed_asset.py`)
- `custom.fixed.asset.depreciation.line` — A single scheduled depreciation entry; holds `posted` flag and link to its `account.move`; exposes `action_post_now()`. (`depreciation_line.py`)
- `custom.fixed.asset.group` — Asset categorisation with default useful life and default asset/accumulated/expense accounts and journal. (`fixed_asset_group.py`)
- `custom.fixed.asset.location` — Hierarchical physical location tree (`_parent_store`, recursive `complete_name`, recursion guard). (`fixed_asset_location.py`)
- `custom.report.asset.register` — `AbstractModel` inheriting `custom.report.engine`; builds the XLSX register report (`_report_code = "asset_register"`). (`custom_report_asset_register.py`)
- `report.custom_accounting_asset.report_asset_register` — `AbstractModel` PDF renderer that reuses the report engine's computed context.
- `custom.fixed.asset.disposal.wizard` — `TransientModel` that computes gain/loss and posts the disposal move. (`wizards/asset_disposal_wizard.py`)
- `custom.report.asset.register.wizard` — `TransientModel` for the report's year/company/group/location/state filters. (`wizards/asset_register_wizard.py`)

## Important Fields
- **custom.fixed.asset**
  - `state` (Selection: draft/running/disposed/cancelled) — Lifecycle state.
  - `acquisition_value`, `salvage_value` (Monetary) — Cost and salvage; depreciable base = acquisition − salvage.
  - `useful_life_months` (Integer, default 60), `depreciation_method` (straight_line/declining/none), `declining_factor` (Float, default 2.0).
  - `asset_account_id`, `depreciation_account_id`, `expense_account_id`, `journal_id` — Account overrides of group defaults.
  - `accumulated_depreciation`, `net_book_value` (Monetary, computed, non-stored) — Sum of posted lines and cost minus that sum.
  - `disposal_date`, `disposal_value`, `disposal_gain_loss`, `disposal_move_id` — Disposal outcome.
- **custom.fixed.asset.depreciation.line**
  - `sequence` (Integer), `date` (Date), `amount` (Monetary).
  - `posted` (Boolean), `move_id` (Many2one account.move) — Posting state and the booked entry.

## Public Methods
- `custom.fixed.asset.action_confirm()` / `action_cancel()` / `action_reset_draft()` — State transitions.
- `custom.fixed.asset.action_open_dispose_wizard()` — Opens the disposal wizard.
- `custom.fixed.asset._post_due_depreciation(as_of=None)` — Posts due lines, one move each.
- `custom.fixed.asset._cron_post_due_depreciation()` — Cron entry point over all running assets.
- `custom.fixed.asset.depreciation.line.action_post_now()` — Manual single-line posting override.
- `custom.fixed.asset.disposal.wizard.action_dispose()` / `_create_disposal_move()` — Disposal + journal entry.

## Integration Points
- **Depends on:** custom_core, custom_pdp_audit, custom_accounting_full, custom_accounting_reports, account.
- **Inherits from:** `custom.fixed.asset` inherits `mail.thread`, `mail.activity.mixin`, `pdp.audited.mixin`; `custom.report.asset.register` inherits `custom.report.engine`.
- **Extended by:** None.
- **External calls:** None.

## Gotchas
- `_build_schedule()` only runs from `action_confirm`. There is no on-change hook that recalculates unposted lines when depreciation parameters change after confirmation; use `action_reset_draft` (only allowed while no line is posted) to rebuild.
- Straight-line and declining schedules absorb the rounding residual into the final line so the total exactly equals the depreciable base.
- Cron discrepancy: `data/ir_cron_data.xml` runs daily (interval 1 day) and its code calls `model._cron_post_depreciation()` guarded by `hasattr`, but the actual method is named `_cron_post_due_depreciation`. As written the cron no-ops; posting must be triggered via the correctly named method or `action_post_now`.

## Out of Scope
- No acquisition journal entry is booked on asset creation (only depreciation and disposal moves are posted).
- No integration with external tax systems.
