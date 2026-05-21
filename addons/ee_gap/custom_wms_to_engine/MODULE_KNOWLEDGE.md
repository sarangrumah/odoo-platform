---
status: draft
generated_at: 2026-05-21T00:00:00Z
generator: claude-code-bootstrap-v1
module: custom_wms_to_engine
manifest_version: 19.0.0.1.0
---

# custom_wms_to_engine

## Purpose
Generic rule-driven **Transfer Order (TO) orchestration engine** for internal warehouse movements. Rules fire on five triggers — low-water mark, expiry approaching, zone consolidation, picking replenishment, and manual — produce proposal dicts, then materialise them as `custom.transfer.order` records backed by `stock.move` internal transfers. Includes a barcoded QWeb pick-slip report and a cron-driven evaluate-and-materialise loop.

## Business Flow
- Warehouse admin creates `custom.to.rule` entries with a `trigger`, optional `warehouse_id`, `source_location_domain` / `target_location_domain` (text, `safe_eval`-evaluated), `priority`, and trigger-specific tuning (`low_water_qty`, `expiry_days_ahead`).
- Cron `custom.to.engine.cron_evaluate_and_materialize()` runs on schedule: `evaluate_all()` loops active rules by `(priority, sequence)`, dispatches to `_eval_<trigger>` handlers, collects proposal dicts, then materialises each as a `custom.transfer.order` in state `proposed`.
- Each `_eval_<trigger>` produces `{rule_id, source_location_id, target_location_id, product_id, lot_id, planned_qty, reason}`:
  - `low_water_mark`: source quants below threshold + a donor quant in target domain → push from donor to deficient location.
  - `expiry_approaching`: lots with `expiration_date <= today + N` routed to a scrap location (or any `usage='inventory'`).
  - `zone_consolidation`: half-bin scraps (≤ 1.0 qty) where target has the same product → merge into home location.
  - `picking_replenishment`: pickings due within 24h staged from move source → first matching target location.
  - `manual`: no proposals; materialised via the manual TO wizard.
- An operator can also call `materialize(proposal_dict)` directly (e.g. from the wizard) to create a TO + its backing `stock.move`.
- A `custom.transfer.order` runs `draft → proposed → in_progress (action_start) → done (action_done)`; `action_cancel` from any state. `picker_id`/`picked_at`/`dropped_at` are stamped on transitions.
- The pick-slip QWeb report (`reports/to_pick_slip_report.xml`) renders a barcoded slip with source/target locations + product/lot/qty.
- `stock.quant.write()` stamps `last_run_at` on all active `low_water_mark` rules whenever `quantity` changes, signalling the cron without running the engine inline (back-pressure).

## Key Models
- `custom.to.rule` — Rule definition; `trigger` + text-domain expressions + priority.
- `custom.transfer.order` — Concrete proposal/execution record; mirrors a `stock.move` 1:1.
- `custom.to.engine` (AbstractModel) — Rule evaluation + materialisation service.
- `stock.quant` (inherited) — Write-hook flags low-water rules for re-evaluation.

## Important Fields
- `custom.to.rule.trigger` (Selection: low_water_mark/expiry_approaching/zone_consolidation/picking_replenishment/manual) — dispatcher key.
- `custom.to.rule.source_location_domain` / `target_location_domain` (Char text) — `safe_eval`-validated Odoo domains; must evaluate to a list.
- `custom.to.rule.low_water_qty` (Float) — threshold for low_water_mark.
- `custom.to.rule.expiry_days_ahead` (Integer, default 7) — lookahead window for expiry trigger.
- `custom.to.rule.priority` (Integer, default 10) — primary order for rule evaluation.
- `custom.to.rule.last_run_at` (Datetime) — stamped by `stock.quant.write` to signal dirty.
- `custom.to.rule.schedule_interval_minutes` (Integer, default 15) — informational; real cron is module-managed.
- `custom.transfer.order.state` (draft/proposed/in_progress/done/canceled).
- `custom.transfer.order.planned_qty` / `actual_qty` — `actual_qty` defaults to `planned_qty` on `action_done`.
- `custom.transfer.order.stock_move_id` (M2o `stock.move`) — backing internal transfer.

## Public Methods
- `custom.to.engine.evaluate_all()` (`@api.model`) — Loop active rules by priority, aggregate proposals.
- `custom.to.engine.evaluate_rule(rule)` — Dispatch to `_eval_<trigger>`.
- `custom.to.engine.materialize(proposal_dict, transfer_order=None)` — Create `stock.move` + TO (if not provided), set TO state to `proposed`.
- `custom.to.engine.cron_evaluate_and_materialize()` — Cron entry: eval + materialise.
- `custom.transfer.order.action_propose()` / `action_start()` / `action_done()` / `action_cancel()` / `action_materialize()` — Workflow + on-demand backing move creation.
- `custom.to.rule._eval_domain(raw)` — Safe domain evaluator; returns `[]` on failure.

## Integration Points
- **Depends on:** `custom_core`, `custom_pdp_audit`, `stock`, `product`, `barcodes`, `mail`.
- **Inherits from:** `mail.thread` + `mail.activity.mixin` + `pdp.audited.mixin` (transfer.order), `mail.thread` + `pdp.audited.mixin` (to.rule), `stock.quant` (write-hook).
- **Extended by:** Warehouse-vertical modules can register additional `_eval_<trigger>` handlers by overriding `custom.to.engine`.
- **External calls:** none.
- **Cross-vertical:** generic; meant as the hub TO engine consumed by all warehouse-bearing verticals.

## Gotchas
- **`stock.quant.write` blindly stamps ALL low-water rules** (no warehouse filter) every time any quant qty changes — high-write workloads will rewrite the entire rule table per inventory move. Safe but inefficient.
- **`_eval_expiry_approaching` requires `stock.lot.expiration_date`** to exist — silently returns `[]` if not (depends on product_expiry being installed).
- **Scrap-location fallback** uses any `usage='inventory'` if no `scrap_location=True` exists — may post variances to the wrong loss bucket.
- **`_eval_zone_consolidation` defines "half-bin" as `quantity <= 1.0`** — flat threshold, ignores UoM. Likely wrong for case-pack products.
- **`_eval_picking_replenishment` uses the first location matching `target_location_domain`** as the single staging target for all moves in scope — no per-product staging.
- **`materialize` doesn't reserve the source quant** — concurrent picks can race the TO; rely on Odoo's `stock.move` confirm/assign to mediate.
- **`cron_evaluate_and_materialize` may create duplicate TOs** if proposals repeat across runs — no dedupe on `(rule, src, tgt, product, lot)`.
- **`action_done` doesn't validate the backing `stock.move`** state; the TO can be marked done while the move is still draft.
- **Domain `safe_eval` uses `{"__builtins__": {}}`** — no `datetime` helpers available inside domain strings.

## Out of Scope
- Wave planning / multi-step orchestration — TOs are single-leg moves.
- Per-line replenishment min/max (only `low_water_qty` threshold).
- Cost / value tracking on the transfer — purely quantity-driven.
- Cross-warehouse transfers — rules and TOs assume internal moves.
- ML-based demand forecasting — triggers are deterministic.
