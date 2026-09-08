---
status: reviewed
generated_at: 2026-08-11
generator: hand-written
module: custom_operating_unit_pos
manifest_version: 19.0.0.1.0
---

# custom_operating_unit_pos — Module Knowledge

## Purpose
Operating-Unit isolation for the point of sale, and the unit on the session
closing entry. Auto-installs where `point_of_sale` and
`custom_operating_unit_docs` are both present.

## Models
- `pos.config` — `operating_unit_id`, computed from `warehouse_id` (never
  overwrites a value already set).
- `pos.session` — `operating_unit_id`, **related stored** to the config, plus
  `_ou_stamp()` and the six vals-hook overrides.
- `pos.order` — computed from its session, falling back to its config.
- `operating.unit` — `pos_config_ids`.

## Why the closing entry is stamped line by line
The move is created on `config_id.journal_id`, a company-wide POS journal with
no unit, so the move→line inheritance has nothing to give. Core produces each
line through its own vals hook, so those are what gets wrapped:
`_get_sale_vals`, `_get_tax_vals`, `_get_combine_receivable_vals`,
`_get_split_receivable_vals`, `_get_invoice_receivable_vals`,
`_get_stock_expense_vals`. `_create_account_move` then puts the unit on the move
itself (under `ou_skip_check`, since it runs for whoever closed the session).

This mirrors `custom_levis_localization/models/pos_session.py`, which stamps the
*analytic* leg of the same dimension on the same lines — the two coexist.

## Gotchas
- The base `pos.config` form shows neither `warehouse_id` nor `picking_type_id`
  (other modules inject those blocks), so the view anchors on
  `//div[@id='title']`.
- The `pre_init_hook` creates `pos_config` / `pos_session` / `pos_order` columns
  before the ORM sees them — `pos_order` is large on a retail tenant and an ORM
  column creation would queue a full-table recompute.
- Because of that, history is filled only by
  `scripts/ops/backfill_operating_unit.py` (config → session → order).
- `domain_force` must stay on one physical line: it is eval'd as Python.

## Related
- `custom_operating_unit_docs` — the mixin, the rules' shape, the same pre-init
  trick.
- `custom_levis_localization` — the analytic leg on the same closing-entry lines.
