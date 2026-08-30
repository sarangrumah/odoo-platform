---
status: draft
generated_at: 2026-08-30T00:00:00Z
generator: claude-code
module: custom_asset_from_receipt
manifest_version: 19.0.0.2.0
---

# custom_asset_from_receipt

## Purpose
Bridge from inventory to the fixed-asset register: a validated goods receipt becomes `custom.fixed.asset` records, in one of two shapes.

- **Per serial number** — 200 drones with 200 serials become 200 assets, optionally with one `rental.asset` each. This is the original purpose of the module and the jalur `custom_rental` depends on.
- **Pooled quantity** — 5 waste bins bought on one non-trade PO line become **one** asset carrying `quantity = 5` and the total value. Broken units are taken out later with *Retire Units* on the asset (see `custom_accounting_asset`).

`custom_asset_stock_link` walks the opposite direction (an existing asset becomes a serial in stock).

## Business Flow
- Flag the product: `is_rental_asset` (serial + rental, legacy) or `is_fixed_asset` with `asset_tracking_mode` ∈ `serial` | `quantity`. Both need `asset_group_id`; only `serial` needs `tracking` in (`lot`, `serial`). `_asset_conversion_mode()` on the template (proxied on `product.product`) resolves the effective mode and is the single place that decides.
- Validate the incoming picking. `stock.picking.has_rental_asset_lines` turns True (done + incoming + at least one convertible product) and shows the **Convert to Assets** header button.
- `action_open_asset_conversion_wizard()` creates `custom.asset.conversion.wizard` and calls `_populate_lines()`:
  - serial products → one wizard line per `stock.move.line` that has a `lot_id`; `unit_cost` from `purchase_line_id.price_unit`.
  - pooled products → move lines aggregated per **(product, purchase line)** into one wizard line carrying the summed `quantity`; `unit_cost` from the PO line, falling back to `product.standard_price` when the receipt has no PO behind it.
- Idempotency: a serial already converted is matched by `lot_id`; a pooled line by (picking, product, lot_id = False, purchase line). Matched lines come back with `existing_asset_id` set, unselected, and are muted in the list.
- `action_confirm()` creates the assets in `draft`, pulling accounts + useful life from the asset group (wizard `asset_group_id` overrides the product's). Pooled: `acquisition_value = unit_cost * quantity`, `quantity`/`original_quantity` set, no lot, no rental asset. Serial: value = one unit's cost, `lot_id` set, and a `rental.asset` created when `create_rental_asset` is on.
- Assets are then confirmed and depreciated by `custom_accounting_asset` as usual; the receipt and the PO both carry a *Fixed Assets* stat button back to them.

## Key Models
- `custom.asset.conversion.wizard` (TransientModel) — header: picking, acquisition date (defaults to `picking.date_done`), optional asset-group override, lines.
- `custom.asset.conversion.line` (TransientModel) — one convertible unit or one pooled bucket; `selected` drives what is created.
- `product.template` / `product.product` (inherit) — the asset flags and `_asset_conversion_mode()`.
- `stock.picking` (inherit) — `has_rental_asset_lines`, `fixed_asset_ids`, the wizard opener.
- `purchase.order` (inherit) — `fixed_asset_ids` computed via `purchase_line_id`.
- `custom.fixed.asset` (inherit) — `lot_id` (unique), `product_id`, `purchase_line_id`, `picking_id`, `rental_asset_ids`.
- `rental.asset` (inherit) — `fixed_asset_id` back-link.

## Important Fields
- `product.template.is_rental_asset` (Boolean) — legacy trigger: one asset **and** one rental unit per serial. Untouched by the pooled mode.
- `product.template.is_fixed_asset` (Boolean) — trigger for plain capex items with no rental side.
- `product.template.asset_tracking_mode` (Selection serial/quantity, default serial, required) — only read when `is_fixed_asset`.
- `product.template.asset_group_id` (M2o `custom.fixed.asset.group`) — required by `_check_rental_asset_config` for any convertible product; supplies life + accounts.
- `custom.asset.conversion.line.conversion_mode` (Selection serial/quantity, readonly) — set by `_populate_lines`, decides what `action_confirm` builds.
- `custom.asset.conversion.line.quantity` (Float) — 1.0 for serial lines, the received total for pooled ones; editable before confirming.
- `custom.asset.conversion.line.unit_cost` / `subtotal` (Monetary) — per-unit cost and `unit_cost * quantity`, which becomes the asset's `acquisition_value` in pooled mode.
- `custom.fixed.asset.lot_id` (M2o `stock.lot`) — `UNIQUE(lot_id)`; NULL for pooled assets, and Postgres allows many NULLs, which is what makes the pooled path fit the same constraint.

## Public Methods
- `product.template._asset_conversion_mode()` / `product.product._asset_conversion_mode()` — `'serial'` | `'quantity'` | `False`.
- `stock.picking.action_open_asset_conversion_wizard()` — done + incoming only.
- `custom.asset.conversion.wizard._populate_lines()` / `action_confirm()` / `action_select_all()` / `action_deselect_all()`.
- `stock.picking.action_view_fixed_assets()` / `purchase.order.action_view_fixed_assets()`.

## Integration Points
- **Depends on:** `stock`, `purchase`, `account`, `custom_accounting_asset`, `custom_rental`.
- **Extended by:** `custom_asset_stock_link` (opposite direction).
- **Cross-vertical:** generic; in production it is installed on `prd_arkaaim` + `trn_arkaaim` (drone register).

## Gotchas
- **`has_rental_asset_lines` is a legacy name** — it now means "this receipt has *any* convertible line", pooled included. The field name is kept because the picking view and existing data reference it.
- **Pooled aggregation keys on (product, purchase line)** — two PO lines for the same product on one receipt deliberately produce two assets, because their unit costs may differ. A receipt with no PO behind it falls back to `standard_price`, which is 0.0 on a product nobody has costed: check the wizard's `unit_cost` before confirming.
- **Serial mode still requires the serials to be assigned on the receipt** — move lines without a `lot_id` are skipped silently, so a partially-serialised receipt converts only what is serialised.
- **`is_rental_asset` and `is_fixed_asset` are independent flags** — `is_fixed_asset` wins when both are set, so a product flagged both with `asset_tracking_mode = quantity` will NOT create rental assets.
- **Conversion does not touch stock valuation** — the assets are an accounting-side subledger; nothing here posts a journal entry. Capitalisation is whatever the PO/bill posted.

## Out of Scope
- **Reversing a conversion** — assets created here are unlinked/cancelled by hand in the asset register; the wizard only detects and skips what already exists.
- **Splitting a pooled asset into per-unit assets** — a pool stays a pool; units only leave through *Retire Units*.
- **Cost re-sync** — a later vendor-bill price correction does not update the asset's `acquisition_value`.
