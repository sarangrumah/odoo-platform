---
status: draft
generated_at: 2026-09-08T00:00:00Z
generator: claude-code
module: custom_service_receipt
manifest_version: 19.0.0.2.0
---

# custom_service_receipt

## Purpose
Let a purchased **service** travel through the goods receipt like a good, so the
vendor bill is gated by an acceptance document instead of a hand-typed quantity.
Built for ARKA-AIM, where subcontracted drone-show work (manpower, venue,
sewa drone, insurance) is bought on POs that produce no receipt at all today, and
where a bill can be raised with `qty_received = 0`.

Opt-in per product. Inert until a product is flagged, so it is safe anywhere.

## Models
- `product.template` inherit — `receive_on_gr` (Boolean). Setting it also forces
  `purchase_method = 'receive'` unless the same write sets the policy itself.
- `product.product` inherit — `_is_service_receipt_product()`:
  `type == 'service' and receive_on_gr`.
- `purchase.order.line` inherit — `_is_service_receipt_line()` plus the three
  reopened core hooks (below).
- `purchase.order` inherit — `_create_picking()` for the all-service order.
- `stock.move` / `stock.move.line` inherit — widened `product_id` UI domain.

## Key mechanics (Odoo 19 specifics — verified against core source)

Core gates **four** places on `product_id.type == 'consu'`; each is reopened:

1. `purchase/models/purchase_order_line.py:219` `_compute_qty_received_method`
   sets `'manual'` for a service. Overridden to `'stock_moves'` for a flagged
   one, so `qty_received` is computed from the moves.
   **`@api.depends` is re-declared, which REPLACES the inherited set** — the base
   triggers (`product_id`, `product_id.type`) are relisted alongside
   `product_id.receive_on_gr`.
2. `purchase_stock/.../purchase_order_line.py:206` `_prepare_stock_moves` returns
   `[]` for a non-good. The override does not call super for a flagged service and
   builds one move: a service is never pulled by a procurement, so core's
   attach/push split collapses to `product_qty - _get_qty_procurement()` with
   `move_dest_ids = False`.
3. `purchase_stock/.../purchase_order_line.py:169` `_create_or_update_picking`
   skips a non-good. Super still runs for the non-service part of the recordset;
   flagged services go through `_service_receipt_create_or_update_picking()`,
   which reproduces core's body for one line (refund activity when the ordered qty
   drops below the billed qty, find-or-create the open receipt, create + confirm +
   assign the moves).
4. `purchase_stock/models/purchase_order.py:378` `_create_picking` only enters its
   loop when the order has at least one goods line. A **mixed** order therefore
   already builds the receipt and hook 2 rides along with it; only the
   **all-service** order needs handling, and the override does that by delegating
   to hook 3 and then confirming + origin-linking the new picking.

Why this is safe on the stock and accounting side, all verified in core:
- **No reservation.** `stock/models/stock_move.py:1839`
  `_should_bypass_reservation()` is true for anything not `is_storable`, so a
  service move is `assigned` the moment it is confirmed — the receipt is never
  stuck waiting.
- **No valuation, no journal entry.** `stock_account/models/stock_move.py:641`
  requires `is_storable` **and** `valuation == 'real_time'`. A service is neither,
  so there is no SVL, no `account_move_id`, and no GR/IR accrual.
- **No quant.** `stock_account`/`stock` only quant storable products.
- The `product_id` domains on `stock.move` (`[('type','=','consu')]`) and
  `stock.move.line` (`[('type','!=','service')]`) are **field-level UI domains
  only**, not constraints; widening them by exactly the flag is enough to let a
  warehouse user add a flagged service to a transfer by hand.

## Flagging a product that already has orders in flight
`_compute_qty_received_method` recomputes **every line that ever used the product**,
confirmed orders included. Taking those over is destructive: a line confirmed
before the flag existed has no receipt and can never be given one, because core
only builds receipts at confirmation. Switching it would zero a hand-typed
`qty_received`, leaving the order unbillable — or bill-negative where it was
already invoiced.

So the override only claims a line when a receipt can actually answer for it:
`order_id.state in ('draft', 'sent')` **or** the line already has `move_ids`.
Core takes the same care — `purchase_stock._update_qty_received_method()`
recomputes every order *except* the confirmed ones.

Two things the flag still changes on live orders, by design and unavoidably:
- **`purchase_method` moves to `receive`.** A line already billed on ordered
  quantities with nothing received goes to `qty_to_invoice = -1`. That is the
  policy change surfacing an inconsistency, not a bug — record the receipt or
  the received quantity first.
- **A confirmed line that already has an open receipt stops being billable until
  that receipt is validated.** That is the whole point of the module.

## Configuration
On the product (Purchase tab, next to the control policy): tick **Receive on
Goods Receipt**. The policy moves to *On received quantities* automatically —
without that, the receipt exists but does not gate the bill, which is the whole
point.

Existing confirmed POs are not retro-fitted: they were confirmed under the old
rule and have no moves. Flag the product, then confirm new orders.

## Tests
`tests/test_service_receipt.py` — flag/policy syncing, unflagged services keeping
core behaviour, all-service and mixed orders building one receipt, partial
receipt, quantity increase joining the open receipt, no journal entry / no quant,
and `qty_to_invoice` following the accepted quantity.

## Related
- `custom_accounting_full` three-way match reads `po_line.qty_received`
  (`models/account_move_match.py:68`), so it starts working for services with no
  change once the quantity comes from a receipt.
- `custom_asset_from_receipt` was hardened alongside this module: putting a
  service on a receipt would otherwise have offered it for capitalisation as a
  fixed asset. `_populate_lines` now asks `product._can_be_fixed_asset()` before
  reading the conversion mode, so no tenant override can reintroduce it.
- `custom_arka_aim_purchase_type` (not on `main` at the time of writing) carries
  the Trade / Non-Trade stream onto the receipt; a service receipt inherits it
  like any other. Its wizard override answers `"quantity"` for every unconfigured
  product on a Non-Trade receipt — which is exactly why the guard above sits
  ahead of the extension point rather than inside it.
- Product **type** is left alone on purpose: `custom_coretax_export`
  (`models/coretax_fk_builder.py:210`) reads `product.type == 'service'` to fill
  the e-Faktur `BARANG_JASA` column. Converting services to non-storable goods —
  the no-code alternative — would misclassify any product that is also sold.
