---
status: draft
generated_at: 2026-05-21T00:00:00Z
generator: claude-code-bootstrap-v1
module: custom_wms_putaway
manifest_version: 19.0.0.1.0
---

# custom_wms_putaway

## Purpose
Generic, configurable, tier-prioritised **putaway engine** that closes the CE-vs-EE gap for SAP-style ZWME001 multi-tier slotting. On every incoming `stock.move.line` create, the engine evaluates all active rules of all active strategies for the destination warehouse, scores them per kind, and either auto-rewrites `location_dest_id` (score > 90) or surfaces a `custom.wms.putaway.suggestion` for operator review (typically through the HHT bridge).

Rule kinds are pluggable: `fixed_location`, `nearest_empty`, `zone_round_robin`, `by_volume`, `by_temperature`, `by_abc_velocity`, and a `safe_eval`-sandboxed `custom_python`. Targeting uses literal `target_location_id` or text-domain expressions (`target_location_domain`, `product_domain`) evaluated at runtime.

## Business Flow
- Warehouse admin creates a `custom.wms.putaway.strategy` per `stock.warehouse`, picking a `rule_set` (default `zwme001_6tier`). Exclusion constraint allows only one active strategy per warehouse.
- Admin adds `custom.wms.putaway.rule` rows under the strategy: each has `tier` (1..6, lower = higher priority), `sequence`, `kind`, optional `target_location_id` / `target_location_domain` / `product_domain`, optional `abc_class`, `temperature_zone`, or `custom_python` expression.
- An inbound `stock.picking` is processed; for every new `stock.move.line` (`StockMoveLine.create`) on an `incoming` picking, `custom.putaway.engine.apply_top_proposal(move_line)` is invoked.
- `propose()` enumerates active rules in `(tier, sequence)` order, calls the matching `_score_<kind>` handler, and collects `{location_id, score, rule_id, reason}` proposals.
- A `custom.wms.putaway.suggestion` row is created with `status=pending`. If the top score > 90, `action_apply()` runs immediately, rewriting `move_line.location_dest_id` and flipping status to `applied`.
- Operator can later `action_accept` / `action_reject`, or set `overridden_location_id` and `action_apply` (status becomes `overridden`).
- `custom.wms.hd.pallet` tracks handling units / pallets with `state` (draft/in_use/empty/scrapped) for volumetric putaway book-keeping.
- `stock.location` is extended with `volume_capacity_m3` and a computed `volume_used_m3` (sum of `quant.quantity * product.volume`); `by_volume` scoring uses these.
- `product.template` gains `abc_class` (A/B/C, default B) for `by_abc_velocity` scoring.

## Key Models
- `custom.wms.putaway.strategy` — Per-warehouse rule container; exactly one active per warehouse.
- `custom.wms.putaway.rule` — Single tiered scoring entry; kind selects the handler.
- `custom.wms.putaway.suggestion` — Engine output awaiting operator decision (pending/accepted/overridden/applied/rejected).
- `custom.putaway.engine` (AbstractModel) — Scoring + auto-apply service; entry point `propose()` and `apply_top_proposal()`.
- `custom.wms.hd.pallet` — Handling unit / pallet tracker with barcode, location, volume.
- `stock.location` (inherited) — Adds `volume_capacity_m3` / `volume_used_m3`.
- `stock.move.line` (inherited) — `create()` override auto-proposes on incoming pickings.
- `product.template` / `product.product` (inherited) — Adds `abc_class`.

## Important Fields
- `custom.wms.putaway.strategy.rule_set` (Selection: zwme001_6tier/abc/fefo/custom) — semantic tag; ZWME001 constrains rule tier to [1,6].
- `custom.wms.putaway.strategy.auto_apply_suggestions` (Boolean) — kill-switch; if True, suggestion is auto-applied regardless of score.
- `custom.wms.putaway.rule.tier` (Integer, default 1) — lower wins; strict tier ordering inside a strategy's `_suggest_putaway`.
- `custom.wms.putaway.rule.kind` (Selection) — dispatches to `_score_<kind>` on the engine.
- `custom.wms.putaway.rule.target_location_domain` / `product_domain` (Char text) — `safe_eval`-evaluated Odoo domains.
- `custom.wms.putaway.rule.custom_python` (Text) — sandboxed expression; must return `(location_id, score_int_0_100)`.
- `custom.wms.putaway.rule.abc_class` / `temperature_zone` — declarative filters used by ABC + temperature handlers.
- `custom.wms.putaway.suggestion.score` (Integer 0..100) — confidence; >90 triggers auto-apply.
- `custom.wms.putaway.suggestion.status` (Selection) — pending/accepted/overridden/applied/rejected.
- `stock.location.volume_capacity_m3` (Float) — gating capacity for `by_volume`.
- `product.template.abc_class` (A/B/C) — ABC velocity classification, default B.

## Public Methods
- `custom.putaway.engine.propose(move_line)` — Ranked proposals across all active strategies/rules in `(tier, -score)` order.
- `custom.putaway.engine.apply_top_proposal(move_line)` — Creates suggestion; auto-applies if score > 90.
- `custom.putaway.engine._score_rule(rule, move_line)` — Dispatcher to per-kind scorer; defensive try/except.
- `custom.wms.putaway.strategy._suggest_putaway(move_line)` — Tier-strict alternative entry that respects `auto_apply_suggestions`.
- `custom.wms.putaway.suggestion.action_apply()` / `action_accept()` / `action_reject()` — Operator workflow.
- `custom.wms.putaway.rule._candidate_locations()` — Resolves internal locations matching `target_location_domain`.
- `custom.wms.putaway.rule._matches_product(product)` — ABC + `product_domain` filter.

## Integration Points
- **Depends on:** `custom_core`, `custom_pdp_audit`, `custom_barcode`, `stock`, `product`.
- **Inherits from:** `stock.move.line` (incoming create-hook), `stock.location` (volumetrics), `product.template` + `product.product` (ABC class), `mail.thread` + `pdp.audited.mixin` (on strategy/rule/suggestion).
- **Extended by:** `custom_hht_bridge` (suggestion review at HHT), and any warehouse-vertical that adds a new `kind` or custom_python helpers.
- **External calls:** none.
- **Cross-vertical:** generic — module description explicitly states "no warehouse-vertical assumptions."

## Gotchas
- **Hardcoded auto-apply threshold (`> 90`)** in `apply_top_proposal()` — not a config parameter; rules must score precisely above 90.
- **`_check_zwme001_tiers` only validates [1,6]** when `rule_set='zwme001_6tier'`. Other rule_sets accept any positive tier.
- **`_score_zone_round_robin` cannot rewrite the target location** (no per-record state) — it scores 70 but the suggestion still uses `rule.target_location_id`. Round-robin behaviour is effectively cosmetic.
- **`stock.move.line.create()` swallows engine errors** with `_logger.warning` — auto-putaway failures never block the inbound transfer, but also never surface to the operator beyond log entries.
- **`safe_eval` for domains uses `{"__builtins__": {}}`** — perfectly safe but means you cannot reference helpers like `datetime` inside a domain string.
- **`volume_used_m3` is not stored** (`store=False`); recomputed on every read, can be slow on dense locations.
- **`_score_nearest_empty` distance heuristic is a stub** — comment says "Score by lexical proximity to dock (lower id ~ closer)"; in practice it just returns the first empty match at score 85.
- **`auto_apply_suggestions` on the strategy and the `> 90` engine threshold are independent paths** — `_suggest_putaway` (strategy-driven) vs `apply_top_proposal` (engine-driven). The `stock.move.line.create` hook uses the engine path only.
- **Exclusion constraint uses PostgreSQL `EXCLUDE`** (`uniq_active_strategy_warehouse`) — requires `btree_gist`-style support via plain equality, ships unconditionally.

## Out of Scope
- Outbound/picking putaway — `_is_incoming()` gates the hook to `picking_type_id.code == 'incoming'`.
- Slotting analytics / re-slotting cron — engine is reactive on create only.
- Multi-location move-line splitting — proposals choose a single `location_id`.
- Real distance/zone graph — `nearest_empty` and `zone_round_robin` are heuristic stubs.
- Cross-warehouse putaway — strategies are bound to one `warehouse_id`.
