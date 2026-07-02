---
status: draft
generated_at: 2026-07-02T08:21:50Z
generator: bootstrap-v1
module: custom_wms_to_engine
manifest_version: 19.0.0.1.0
---

# custom_wms_to_engine

## Purpose
The `custom_wms_to_engine` module implements a rule-driven internal transfer orchestration system for warehouse management systems (WMS). It evaluates predefined rules based on various triggers such as low water mark, expiry approaching, zone consolidation, and picking replenishment. These rules are evaluated by the engine and materialized into concrete transfer orders (`custom.transfer.order`) that can be executed manually or automatically.

## Business Flow
1. **Rule Definition**: Admins define rules with conditions for source and target locations using domain expressions.
2. **Evaluation**: The `evaluate_all` method in `ToEngine` model runs all active rules based on their priority order.
3. **Proposal Generation**: For each rule, the engine generates a proposal dict containing details like source and target location IDs, product ID, planned quantity, etc.
4. **Materialization**: The proposals are materialized into transfer orders using the `materialize` method in `ToEngine`.
5. **Execution**: Transfer orders can be manually started or left to run automatically based on their state.

## Key Models
- **custom.to.engine** — Abstract model for the engine that evaluates and materializes transfer order rules.
  - Methods: `evaluate_all`, `evaluate_rule`, `_eval_*` (trigger evaluators), `materialize`
- **custom.transfer.order** — Concrete internal movement proposal/execution.
  - Fields: `name`, `rule_id`, `company_id`, `state`, `source_location_id`, `target_location_id`, `product_id`, `lot_id`, `planned_qty`, `actual_qty`, `picker_id`, `picked_at`, `dropped_at`, `stock_move_id`
- **custom.to.rule** — Rule definition for transfer orders.
  - Fields: `name`, `sequence`, `active`, `company_id`, `warehouse_id`, `trigger`, `source_location_domain`, `target_location_domain`, `product_filter_json`, `low_water_qty`, `expiry_days_ahead`, `schedule_cron`, `priority`, `last_run_at`, `schedule_interval_minutes`

## Important Fields
- **custom.to.rule**
  - `name` (Char) — Rule name.
  - `trigger` (Selection: low_water_mark, expiry_approaching, zone_consolidation, picking_replenishment, manual) — Trigger type.
  - `source_location_domain`, `target_location_domain` (Char) — Domain expressions for source and target locations.
- **custom.transfer.order**
  - `name` (Char) — Order name.
  - `state` (Selection: draft, proposed, in_progress, done, canceled) — State of the transfer order.
  - `source_location_id`, `target_location_id` (Many2one to stock.location) — Source and target locations.
  - `product_id` (Many2one to product.product) — Product being transferred.

## Public Methods
- **custom.to.engine**
  - `evaluate_all()` — Evaluates all active rules in priority order.
  - `evaluate_rule(rule)` — Evaluates a single rule based on its trigger type.
  - `_eval_*` methods (e.g., `_eval_low_water_mark`, `_eval_expiry_approaching`) — Specific evaluators for different triggers.
- **custom.transfer.order**
  - `action_propose()` — Sets the state to proposed.
  - `action_start()` — Starts the transfer order execution.
  - `action_done()` — Marks the transfer as done and updates actual quantity.
  - `action_cancel()` — Cancels the transfer order.
  - `action_materialize()` — Creates a backing stock.move record.

## Integration Points
- **Depends on**: custom_core, custom_pdp_audit, stock, product, barcodes, mail
- **Inherits from**: stock.quant (marks low-water mark rules for re-evaluation)
- **Extended by**: None specified in the manifest.
- **External calls**: None specified in the code.
- **Cross-vertical**: Deployed in arkaim, jds, ppob

## Gotchas
- The engine does not run evaluations inline; it marks relevant rules as "dirty" and relies on a cron job to pick them up.
- Domain expressions for source and target locations are evaluated at runtime using `safe_eval`, which can be error-prone if not carefully crafted.

## Out of Scope
- This module does not cover external integration points or cross-vertical deployments beyond the specified domains. It focuses solely on internal transfer order management within a single warehouse context.
