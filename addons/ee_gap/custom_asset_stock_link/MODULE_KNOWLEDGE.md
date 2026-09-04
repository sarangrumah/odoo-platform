---
status: authored
module: custom_asset_stock_link
manifest_version: 19.0.1.0.0
---

# custom_asset_stock_link

## Purpose

Lets a fixed asset that already exists in the register also live in inventory as
a serial number, so the physical unit can be located, moved between warehouses
and offered for rent — **without any stock valuation reaching the general
ledger**.

`custom_asset_from_receipt` already walks the other direction (goods receipt →
fixed asset). This module covers the case where the assets came first: loaded
from an opening-balance sheet, or capitalised by hand, with no purchase document
behind them.

## Business Flow

1. **Map the locations.** `custom.fixed.asset.location` gains
   `stock_location_id`, tying the accounting-side asset location tree to real
   warehouse locations.
2. **Materialise.** Select assets in the register → *Action → Materialise Into
   Stock*. Per asset the wizard creates (or reuses):
   - one serial-tracked, zero-cost `product.product` per (company, asset name);
   - one `stock.lot` named after the asset code;
   - an inventory adjustment putting 1 unit in the destination location;
   - optionally one `rental.asset` linked back through `fixed_asset_id`.
   It then writes `product_id` / `lot_id` (and `serial_number` where a tenant
   module defines it) onto the asset.
3. **Track.** Every validated stock move refreshes the asset's
   `stock_location_id` / `stock_state` / `stock_qty`.
4. **Rent.** `is_rentable` answers "which units are free right now"; the
   `custom_rental` pickup/return flow moves the serial in and out.

## Models

| Model | Change |
|---|---|
| `custom.fixed.asset.location` | `stock_location_id` — the warehouse location this asset location represents |
| `custom.fixed.asset` | `stock_location_id`, `stock_state`, `stock_qty`, `stock_synced_on` (stored, auto-maintained), `move_line_count`, `rental_asset_id`, `rental_state`, `is_rentable` |
| `stock.lot` | `fixed_asset_ids` + smart button back to the register |
| `stock.move.line` | `_action_done` override — the single sync choke point |
| `rental.asset` | `lot_id`, `stock_location_id`, `is_available_now` (all related/stored) |
| `rental.order` | `_resolve_picking_type_and_locations` + `_create_stock_picking` overrides — ship the unit from where it is, with its serial |
| `custom.asset.stock.materialize.wizard` | the bulk materialisation wizard |

## Key Decisions

**`location_id` is never written.** The accounting-side asset location belongs
to Finance and is what `custom_ops_reports`' asset opname report prints. The
warehouse position lives in `stock_location_id` alongside it. The two are
allowed to disagree; that disagreement is itself the useful signal.

**Zero valuation, enforced three ways.** In Odoo 19 stock only reaches the
ledger through `stock_account.stock_move._should_create_account_move()`, which
requires *all* of: a storable valued product, a location with a
`valuation_account_id`, and `product.valuation == 'real_time'`. So:

- products are filed in `product_category_fixed_asset_non_valued`, pinned to
  `property_valuation = 'periodic'` **per company** (the field is
  `company_dependent`, and an unset value silently falls back to
  `res.company.inventory_valuation`);
- products carry `standard_price = 0.0` — this is what also keeps the *periodic*
  year-end valuation entry at nil, which `periodic` alone would not;
- `_assert_zero_valuation` refuses to run if the company, the category, any
  product or any destination location would value the stock. It runs twice:
  before creating products, and again after, in case a pre-existing product was
  misconfigured.

Odoo 19 spells the selection `periodic` / `real_time`. Code written against the
older `manual_periodic` never matches and silently passes.

**Serial identity is the asset code.** Registers built from spreadsheets
normally have a blank `serial_number`, and the asset code is unique per unit.
`serial_number` is only written when a tenant module defines the field.

**The sync is stored, not computed.** A compute over thousands of assets makes
list views and group-by unusable. `stock.move.line._action_done` refreshes the
affected assets (one `read_group` per batch, never per record); a nightly cron
(`_cron_sync_stock_locations`) is the safety net for changes made outside the
ORM. Pass `skip_asset_stock_sync=True` in the context to suppress the hook
during bulk loads and sync once at the end.

**Loans ship from the unit's real location.** `custom_rental` sources a loan
picking from the first internal picking type's default location — in a
multi-step warehouse that is the Input dock, not the shelf the drone is on.
Validating from there books a negative quant on the dock and leaves the unit
where it was, silently. For asset-backed rentals this module overrides
`_resolve_picking_type_and_locations` to use the serial's actual location as the
source, the warehouse's own `int_type_id`, and — on return — the accounting asset
location's mapped stock location as the destination (stable across the loan,
unlike the unit's current position).

## Gotchas

- Materialisation is **idempotent per asset**: anything already carrying a
  `lot_id` is skipped, and `custom.fixed.asset` has `UNIQUE(lot_id)` from
  `custom_asset_from_receipt`. Re-running with only-linked assets raises a
  `UserError` rather than doing nothing silently.
- Products are created fresh under a `FA/` prefix. Do not point the wizard at
  pre-existing untracked products: Odoo blocks flipping `tracking` to `serial`
  once a product has stock moves.
- `is_rentable` requires the asset to be `running`. Draft register rows get a
  serial and a location but stay off the rental floor, which is the intent.
- A bare database has every internal picking type inactive and multi-location
  off; the tests switch both on.

## Related

- `custom_asset_from_receipt` — the receipt → asset direction, and the origin of
  `lot_id` / `product_id` / `rental_asset_ids`.
- `custom_rental` — `rental.asset` availability and the pickup/return pickings.
- `scripts/tenants/arkaaim/materialize_assets_to_stock.py` — the ARKA/AIM
  backfill; `verify_asset_stock_link.py` checks the result.
