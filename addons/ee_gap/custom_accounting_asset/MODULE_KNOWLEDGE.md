---
status: draft
generated_at: 2026-05-21T00:00:00Z
generator: claude-code-bootstrap-v1
module: custom_accounting_asset
manifest_version: 19.0.0.1.0
---

# custom_accounting_asset

## Purpose
Fixed-asset register for Odoo CE — closes the EE `account_asset` gap. Maintains a per-company asset master file with hierarchical locations and groups (each with default useful life + default G/L accounts), generates straight-line or double-declining depreciation schedules, and runs a monthly cron that posts `DR depreciation_expense / CR accumulated_depreciation` journal entries for due lines. A disposal wizard captures sale value, computes gain/(loss) vs NBV, and books the retirement entry.

This is the canonical FA module. Anything BRD-related to "aset tetap", "penyusutan", "depreciation schedule", "disposal", "NBV" lives here.

## Business Flow
- Set up a `custom.fixed.asset.group` (default useful life, default asset/accum/expense accounts, default journal).
- Set up a `custom.fixed.asset.location` tree (`_parent_store=True`, recursive `complete_name`).
- Create a `custom.fixed.asset` in `draft`; `code` auto-assigned from `ir.sequence("custom.fixed.asset")`. `_onchange_group_id` copies group defaults into asset.
- `action_confirm()` requires expense + accumulated + journal accounts when `depreciation_method != "none"`; calls `_build_schedule()` then transitions `draft`→`running`. The schedule generator writes `custom.fixed.asset.depreciation.line` rows from `acquisition_date + relativedelta(months=n)` for `useful_life_months` periods. Straight-line uses `round(remaining/months_left, 2)` per month with rounding residual absorbed in the last line; declining uses `factor/total_months * NBV` with straight-line residual on the final period.
- Monthly cron `_cron_post_due_depreciation` (calls `_post_due_depreciation()`): walks all `state='running'` assets, posts each unposted line whose `date <= today` as one `account.move` per line (DR expense / CR accumulated), flips `line.posted=True` and `line.move_id`.
- `action_open_dispose_wizard()` (running-only) opens `custom.fixed.asset.disposal.wizard`. The wizard computes `gain_loss = disposal_value - net_book_value` and, on `action_dispose()`, creates a balanced retirement move: DR accum + DR proceeds + DR loss / CR asset cost + CR gain. Asset is written to `disposed` with `disposal_date`, `disposal_value`, `disposal_gain_loss`, `disposal_move_id`.
- `action_cancel()` allowed only if no depreciation has posted; `action_reset_draft()` unlinks all schedule lines and reverts to draft.
- Manual single-line posting via `custom.fixed.asset.depreciation.line.action_post_now()` (delegates to `_post_due_depreciation(as_of=line.date)`).

## Key Models
- `custom.fixed.asset` — asset master (acquisition + accounts + state machine + schedule O2m). Inherits `mail.thread` + `mail.activity.mixin` + `pdp.audited.mixin`.
- `custom.fixed.asset.group` — category w/ default useful life + default accounts + default journal.
- `custom.fixed.asset.location` — hierarchical (`_parent_store`) physical location; computed `complete_name`.
- `custom.fixed.asset.depreciation.line` — one row per scheduled period; `posted` + `move_id` set when GL booked.
- `custom.fixed.asset.disposal.wizard` (TransientModel) — captures disposal_date + disposal_value + gain/loss accounts.

## Important Fields
- `custom.fixed.asset.state` (Selection draft/running/disposed/cancelled) — only `running` is depreciated; `disposed` is terminal.
- `custom.fixed.asset.code` (Char, unique per company via `code_company_unique`) — auto from sequence.
- `custom.fixed.asset.acquisition_value` / `salvage_value` (Monetary) — `_check_salvage` bans `salvage > acquisition` and negatives.
- `custom.fixed.asset.useful_life_months` (Integer, default 60) — must be ≥1 when method ≠ none.
- `custom.fixed.asset.depreciation_method` (Selection straight_line/declining/none) — `none` skips schedule entirely.
- `custom.fixed.asset.declining_factor` (Float, default 2.0) — factor for double-declining (2.0 = DDB).
- `custom.fixed.asset.asset_account_id` / `depreciation_account_id` / `expense_account_id` (M2o `account.account`) — overrides group defaults.
- `custom.fixed.asset.journal_id` (M2o `account.journal`, type=general) — depreciation journal.
- `custom.fixed.asset.accumulated_depreciation` / `net_book_value` (Monetary, computed, non-stored) — `sum(posted lines)` and `acquisition - accum`.
- `custom.fixed.asset.disposal_date` / `disposal_value` / `disposal_gain_loss` / `disposal_move_id` (readonly, set by wizard).
- `custom.fixed.asset.depreciation.line.posted` (Boolean) — gates the cron; once True the line is immutable to the cron.
- `custom.fixed.asset.depreciation.line.sequence` (Integer, required) — drives schedule order; new lines built from `max(sequence)+1`.

## Public Methods
- `custom.fixed.asset.action_confirm()` — validates accounts → builds schedule → state=running.
- `custom.fixed.asset.action_cancel()` / `action_reset_draft()` — both refuse if any line is posted.
- `custom.fixed.asset.action_open_dispose_wizard()` — running-only.
- `custom.fixed.asset._build_schedule()` — preserves posted lines, rebuilds unposted from current parameters.
- `custom.fixed.asset._depreciable_base()` — `max(0, acquisition - salvage)`.
- `custom.fixed.asset._post_due_depreciation(as_of=None)` — posts due unposted lines; one `account.move` per line.
- `custom.fixed.asset._cron_post_due_depreciation()` (`@api.model`) — monthly cron entry.
- `custom.fixed.asset.depreciation.line.action_post_now()` — manual single-line posting.
- `custom.fixed.asset.disposal.wizard.action_dispose()` / `_create_disposal_move()` — builds balanced retirement move.

## Integration Points
- **Depends on:** `custom_core`, `custom_pdp_audit`, `custom_accounting_full`, `account`.
- **Inherits from:** `mail.thread` + `mail.activity.mixin` + `pdp.audited.mixin` on `custom.fixed.asset`; `mail.thread` on disposal wizard not used.
- **Extended by:** none in-tree.
- **External calls:** none.
- **Cross-vertical:** generic.

## Gotchas
- **One `account.move` per depreciation line** — high-volume installations (thousands of assets × monthly) will create a lot of moves. No batching.
- **Schedule preservation is partial** — `_build_schedule` keeps `posted=True` lines but `unlinks all unposted`; if you change `useful_life_months` mid-life, unposted lines are rebuilt with `months_left = months - len(posted lines)`, NOT recalculated from the new total — verify before relying on parameter changes.
- **Declining method falls back to straight-line in the final period** to consume the full base — the last line absorbs the rounding residual; gain/loss arithmetic at disposal depends on this.
- **Rounding fudge** in straight-line: monthly = `round(remaining/months_left, 2)`, final line = `round(remaining - running, 2)`. Total matches `_depreciable_base()` but per-period values do not sum exactly to `monthly * months`.
- **`salvage_value` is captured but NOT booked at disposal** — disposal arithmetic uses NBV (`acquisition - accumulated`), not salvage. If posted depreciation never reaches `base - salvage` (e.g. early disposal), the residual asset cost stays on books via the disposal move's `CR asset_cost = acquisition_value` line.
- **No multi-currency depreciation** — `currency_id` is related from `company_id`; assets in a non-company currency lose precision.
- **`action_cancel` after posted lines is permanently blocked** — must reverse the posted moves manually before retry.
- **Group defaults only apply via `_onchange_group_id`** — record-level write of `group_id` from code does NOT cascade defaults; the UI onchange is the only writer.

## Out of Scope
- **Revaluation / impairment** — no upward/downward revaluation workflow.
- **Componentisation** — one asset = one schedule; no parent/child component depreciation.
- **Asset transfer between companies** — disposal wizard only handles sale/write-off.
- **Tax depreciation parallel ledger** — single schedule only; no tax vs accounting book split.
- **Asset tagging / barcoding** — `code` is human; no `barcode` field. See `custom_hht_bridge` for scanning workflows.
