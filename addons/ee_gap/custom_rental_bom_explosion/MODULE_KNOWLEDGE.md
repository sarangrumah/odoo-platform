---
status: draft
generated_at: 2026-09-02T00:00:00Z
generator: hand-written
module: custom_rental_bom_explosion
manifest_version: 19.0.0.2.0
---

# custom_rental_bom_explosion

## Purpose
Bridges the gap between how a rental bundle is **sold** and how it **moves**. A drone-show package is quoted, ordered and priced as a single line — "Sewa Drone Show 1500 Unit", qty 1 — but the physical reality behind that line is 1500 serial-tracked drones plus their batteries and controllers. This module explodes the rented product's `mrp.bom` (kit / phantom) so the pickings move every component, and the BAST handover document lists them.

Without it, a qty-1 bundle moves exactly one unit of the bundle product: the stock is wrong and the serial reconciliation on return has nothing to check.

## Business Flow
1. A `rental.order` is created for a bundle product (bulk mode `product_id`, or serial mode `asset_id`).
2. On `action_confirm` / `action_return`, `custom_rental` builds the pickup / return picking. This module overrides `_prepare_move_vals_list`, so instead of one move for the bundle it emits **one move per exploded BOM component**.
3. `loan_qty` counts spare **bundles**, not units — it is exploded the same way and its moves carry `is_loan=True`.
4. BAST pickup / return documents list the same components, via `_bast_lines_vals`.
5. On return, `custom_rental._check_returned_serials` reconciles the serials that actually went out — which, thanks to this module, are the components' serials.

If the rented product has no BOM, every path falls back to `custom_rental`'s plain single-product behaviour. Non-bundle rentals are untouched.

## Key Models
- `rental.order` (inherited) — carries the explosion logic. No new fields.
- `rental.asset` (inherited) — adds `bom_id` and `has_bundle`; an asset-level explicit BOM wins over the product's.

## Important Fields
- `rental.asset.bom_id` — optional explicit bundle BOM. Domain is `product_tmpl_id.is_rentable = True`. If empty, resolution falls back to the product's first `phantom` BOM, then its first BOM of any type.
- `rental.asset.has_bundle` — non-stored compute; true when a usable BOM resolves.

## Public Methods
- `rental.order._resolve_bundle_bom()` — the BOM backing this order, or an empty recordset. Serial mode delegates to `rental.asset._resolve_bom()`; bulk mode resolves off `_resolve_rental_product()`, preferring a `phantom` BOM.
- `rental.order._explode_bundle(qty=1.0)` — `[{product, qty, uom}, ...]` for `qty` bundles, or `[]` when there is no BOM. Every caller reads `[]` as "fall back to the plain behaviour".
- `rental.order._prepare_move_vals_list(product, loc_src, loc_dst)` — override; one move per component, main and loan quantities alike.
- `rental.order._bast_lines_vals()` — override; one BAST line per component, loan components prefixed `[LOAN]`.
- `rental.order._populate_bast_from_bom(bast)` — legacy hook, kept for BAST documents created outside `action_generate_bast_*`. Idempotent; skips a BAST that already has lines.
- `rental.asset._resolve_bom()` / `_explode_components(qty=1.0)` — asset-side resolution and explosion.

## Integration Points
- **Depends on:** custom_rental, custom_bast, mrp.
- **Inherits / extends:** `rental.order` (`_prepare_move_vals_list`, `_bast_lines_vals`, `action_generate_bast_pickup/return`), `rental.asset` (`bom_id`, `has_bundle`).
- **Extended by:** None.
- **External calls:** `mrp.bom.explode()`, with a direct `bom_line_ids` iteration as fallback.

## Gotchas
- **Before 19.0.0.2.0 this module never fired at all.** `custom_rental.action_generate_bast_*` fills `line_ids` from `_bast_lines_vals()` at create time, so the post-create `_populate_bast_from_bom` hook always hit its `if bast.line_ids: return` guard — in serial mode too, not only bulk. The explosion now happens in `_bast_lines_vals` itself, one code path for both.
- **The BOM's own `product_qty` matters.** A phantom BOM that declares it produces N packages divides the line quantities by N on explosion. A per-package BOM must set `product_qty = 1`, or 500 drones per package become 1.
- **A component's UoM can differ from the product's default**; `_stock_move_vals` takes the BOM line's `product_uom_id`, so do not assume `product.uom_id`.
- Explosion depends on `_resolve_rental_product()`. When an intercompany asset-loan spawns the rental order, `account.intercompany.rule.loan_asset_product_id` must therefore point at the **bundle** product, not at the physical unit — a bare unit has no BOM and nothing explodes.
- The picking's source location still comes from the picking type (or, in internal-loan mode, its `default_location_src_id`). Explosion does not change where the components are sourced from; if the fleet does not live there, the moves will not reserve.

## Out of Scope
- Does not create or maintain BOMs — they are configuration.
- Does not explode into sub-rentals or per-serial rental orders; one rental order still covers the whole bundle.
- Does not touch pricing: the bundle line's rate is unchanged, components carry no price.
