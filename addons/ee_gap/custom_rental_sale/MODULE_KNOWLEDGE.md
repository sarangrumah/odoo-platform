---
status: authored
module: custom_rental_sale
manifest_version: 19.0.1.0.0
---

# custom_rental_sale

## Purpose

ARKA-AIM sells drone shows through Sales: one line, `Jasa Drone Show 1500 Unit`,
quantity 1, priced as a lump sum for the event. Behind that line sit 1,500
serial-tracked drones that physically leave the shelf and have to come back.

`rental.order` already knows how to dispatch and reconcile serials, but it prices
by `daily_rate × days × qty` and accrues daily late fees — a commercial model
that does not fit a fixed-price show. So this module does **not** move selling
onto rental. The sales order stays the commercial document and the source of
revenue; rental contributes only the part Sales cannot do.

Evidence for the split: at the time of writing, `prd_arkaaim` had 11 sales orders
and **zero** rental orders, while `custom_rental_bom_explosion` — a module whose
own description names the 1,500-drone bundle case — had never been reached.

## Business Flow

1. **Sell as usual.** Quotation, show date, event name, BAST, numbering, down
   payments, tax — untouched. The Deployment tab is Ops' side of the same event.
2. **Confirm.** With `deployment_auto_create` on, confirming a sales order that
   names a deployment product creates one `rental.order` in **draft**. Draft on
   purpose: dispatching is an act the warehouse performs when it is ready, not a
   side effect of a salesperson clicking Confirm.
3. **Dispatch.** Ops confirms the deployment; the outbound picking moves units
   Stock → On-Deployment, inside the company's own location tree.
4. **Return.** The units come back; Ops validates the return picking.
5. **Reconcile.** Serials that did not come back are proposed as missing; serials
   that came back broken are marked damaged. Both are handed to
   `custom_asset_lifecycle`.

## Two guards, not features

**A deployment cannot carry money.** `daily_rate` and `deposit_amount` must stay
zero, and `action_create_invoice` refuses outright. The sales order bills the
event; a second document able to bill the same thing is how a customer gets
charged twice. `custom_rental_invoicing`'s auto-invoice-on-return catches the
UserError and notes it on the order, so a deployment that reaches that path
leaves a trail instead of an invoice.

**Units never reach a customer location.** Deployments run in
`is_internal_loan` mode: Stock → On-Deployment and back, both internal. Nothing
is delivered and nothing is sold, so no COGS and no valuation journal can result.

## Gotchas

**Dispatch must be sourced from where the fleet actually lives.**
`custom_rental` sources an internal loan from the *first* internal picking type's
`default_location_src_id` — the Input dock in a multi-step warehouse, and not
where ARKA-AIM's drones sit. Reserving from a location the units are not in does
not fail. It books `-1` at the source, `+1` at the destination, and leaves the
original stock untouched: the unit is now in two places, silently. That is
exactly the pattern that had 2,572 of the 3,590 units reporting the wrong
warehouse (see `custom_asset_stock_link` 19.0.1.2.0).

`custom_asset_stock_link` already corrects this for single-serial rentals by
reading the asset's own position. A deployment is bulk mode — one bundle standing
for hundreds of serials — so there is no single asset to ask, and the source has
to come from configuration: `res.company.deployment_source_location_id`, falling
back to the on-deployment location's warehouse stock location.
`test_dispatch_picks_from_where_the_units_are` asserts no negative quant is left
behind and that the serial ends up in exactly one place.

**The same latent bug still applies to bulk-mode internal loans that are not
deployments.** The fix here is scoped to deployments deliberately: `custom_rental`
serves other tenants whose loan flows are not covered by these tests, and
silently repointing their source location is not a change to make blind.

**A serial mismatch used to be a dead end.**
`custom_rental._check_returned_serials` raised a `UserError` listing the missing
serials and advising "resolve via inventory adjustment or pursue claim". An
inventory adjustment is how a lost drone stops being anybody's problem, which is
the opposite of what the register needs. `action_validate_loan_return` now routes
a mismatch to the reconciliation wizard — but **only when the serials are fixed
assets** it can actually book. A mismatch on serials outside the register still
raises the original hard error, because for those the complaint is the right
answer.

**The wizard lists discrepancies only.** A show dispatches 1,500 serials; asking
an operator to tick 1,500 boxes to say "all fine" guarantees the feature goes
unused. Serials that returned normally need no decision, so they get none.

**Sales settings block anchor.** The `sale` settings view has no
`quotation_order_setting_container` block; the Deployments block hangs off
`pricing_setting_container`.

## Models

| Model | Role |
|---|---|
| `sale.order` (inherit) | Deployment product, quantity, spares, window, location; create + view deployments; auto-create on confirm |
| `rental.order` (inherit) | `sale_order_id` / `is_deployment`, the money and invoicing guards, the corrected dispatch source, the return-reconciliation entry point |
| `res.company` / `res.config.settings` | `deployment_auto_create`, on-deployment location, deployment source location |
| `custom.rental.return.reconcile.wizard` (+ `.line`) | What happened to the units that did not come back the way they went out |

## Configuration

Sales ▸ Configuration ▸ Deployments: tick *Create Deployments From Sales Orders*,
set the **on-deployment** location and the **source** location. For ARKA-AIM the
source is `WH/RUKO GUDANG PALEM`, not `WH/Stock` — that is where the fleet lives.
Leaving the feature off leaves Sales behaving exactly as it does today.

The damage and lost/missing locations come from `custom_asset_lifecycle`
(Accounting Settings ▸ Asset Lifecycle) and are already configured on
`prd_arkaaim`.

## Tests

`tests/test_rental_sale.py` — 13 tests. The bridge (a confirmed sale creates a
money-free draft deployment; opting out leaves Sales untouched; a missing
location notes the order rather than blocking the sale; the window defaults from
the show date), the guards (a deployment cannot carry a rate, cannot invoice
itself), the dispatch (sourced from the right location, no negative quants), and
the reconciliation (a serial that never came back becomes a missing asset that
keeps depreciating; one that came back broken becomes a damaged asset with a
repair order; the sale is told; leaving everything open books nothing; a clean
return still closes the old way).
