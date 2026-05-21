---
status: draft
generated_at: 2026-05-20T18:39:01Z
generator: bootstrap-v1
module: custom_rental
manifest_version: 19.0.0.2.0
---

# custom_rental

## Purpose
Provides the end-to-end lifecycle for **asset-based equipment rental**: an inventory of rentable physical assets (`rental.asset`), per-product multi-tier pricing (`custom.rental.pricing`), a workflow-driven rental order (`rental.order`) with overlap protection, late-fee cron accrual, BAST (handover) integration, customer e-signature capture, stock picking generation, and a customer portal for self-service viewing/signing.

It is the canonical rental module in the platform — anything related to renting a single, serialisable, returnable physical asset to a customer for a date window should live here or extend here.

## Business Flow
- A manager registers a rentable asset on `rental.asset` (state `available`), optionally linked to a `product.product` for stock integration, with `daily_rate` and `deposit_amount`.
- A product manager configures `custom.rental.pricing` tiers (hour/day/week/month @ price) on `product.template` (gated by `is_rentable`).
- A user creates a `rental.order` in `draft`; sequence `rental.order` assigns the `name`. If `daily_rate` is empty it is auto-copied from the asset on create.
- `action_confirm()` enforces draft→`confirmed`, writes a `pdp.audited.mixin` audit entry, and (if `custom_rental.config_stock_integration` is enabled and the asset has a `product_id`) creates an outbound `stock.picking` via `_create_stock_picking('outgoing')`.
- `_check_overlap()` constraint blocks any other `confirmed`/`picked_up` order on the same `asset_id` for an intersecting `[pickup_dt, return_dt_expected)` window.
- `action_pickup()` moves `confirmed`→`picked_up`, flips `rental.asset.state` to `on_rent`.
- A daily cron iterates `picked_up` orders past `return_dt_expected` and appends a `custom.rental.late.fee.line` row per day, bumping `late_fee_total` (one row per `(order_id, accrued_on)`).
- `action_return()` moves `picked_up`→`returned`, stamps `return_dt_actual = now()`, flips asset back to `available`, recomputes `days_actual` / `rental_fee` / `late_penalty` (50% surcharge on overrun days, distinct from cron `late_fee_total`), and creates an inbound `stock.picking`.
- `action_cancel()` is allowed from any state except `returned`; releases asset if it was `on_rent`.
- The portal lets the customer view `/my/rentals`, download the rental contract PDF (`custom_rental.action_report_rental_contract`), and POST a base64 signature to `/my/rentals/<id>/sign` which writes `customer_signature`, `customer_signed_by`, `customer_signed_at`.
- BAST documents are attached via `bast_pickup_id` / `bast_return_id` (provided by `custom_bast`).
- `custom.rental.schedule` exposes a read-only SQL view for calendar/Gantt UIs, computing a derived `late` pseudo-state when `picked_up` runs past `return_dt_expected`.

## Key Models
- `rental.asset` — Physical rentable unit; tracks `state` (available/on_rent/maintenance/retired), `daily_rate`, `deposit_amount`, optional link to `product.product` for stock moves.
- `rental.order` — The transactional record; one asset, one customer, one date window. Inherits `mail.thread`, `mail.activity.mixin`, `pdp.audited.mixin` (classification `financial`).
- `custom.rental.pricing` — Per-`product.template` pricing tier (duration × unit × price). Multiple tiers per product; `_get_rental_price` picks the cheapest combination.
- `custom.rental.late.fee.line` — Daily accrual audit row written by the late-fee cron; uniqueness `(order_id, accrued_on)`.
- `custom.rental.schedule` — `_auto=False` SQL view over `rental_order` for calendar/Gantt; aliases `order_id` as `line_id` reserved for future multi-line support.
- `product.template` (inherited) — Adds `is_rentable` flag and `rental_pricing_ids`.
- `res.config.settings` (inherited) — Holds `rental_stock_integration` and `rental_default_late_fee_rate` ir.config_parameters.

## Important Fields
- `rental.order.state` (Selection: draft/confirmed/picked_up/returned/cancelled) — drives the entire workflow; transitions guarded by `action_*` raising `UserError`.
- `rental.order.asset_id` (M2o `rental.asset`, domain excludes retired) — the rented unit; overlap constraint pivots on this.
- `rental.order.pickup_dt` / `return_dt_expected` / `return_dt_actual` (Datetime) — booking window; `return_dt_actual` is stamped automatically by `action_return`.
- `rental.order.days_planned` / `days_actual` (Float, computed, stored) — clamped to minimum 1.0 day; the divisor is 86400 seconds.
- `rental.order.rental_fee` / `late_penalty` / `total_due` (Monetary, computed) — `late_penalty` uses a hardcoded **50% surcharge** on overrun days; `total_due` sums all three including cron-accrued `late_fee_total`.
- `rental.order.late_fee_rate` (Float, default from `custom_rental.default_late_fee_rate`) — per-day percentage used by the accrual cron.
- `rental.order.late_fee_total` (Monetary, readonly) — cumulative cron-driven late fee, distinct from compute-time `late_penalty`.
- `rental.order.bast_pickup_id` / `bast_return_id` (M2o `custom.bast.document`) — handover documents, filtered by `kind`.
- `rental.order.customer_signature` (Binary) + `customer_signed_by` (Char) + `customer_signed_at` (Datetime) — portal-captured e-signature.
- `rental.order.pickup_picking_id` / `return_picking_id` (M2o `stock.picking`, readonly) — auto-generated stock moves.
- `rental.asset.state` (Selection: available/on_rent/maintenance/retired) — kept in sync with order workflow via `sudo()` writes.
- `custom.rental.pricing.unit` (Selection: hour/day/week/month) — combined with `duration` via `UNIT_TO_HOURS` (month = 30 days).

## Public Methods
- `rental.order.action_confirm()` — draft→confirmed, audit log, creates outbound `stock.picking`.
- `rental.order.action_pickup()` — confirmed→picked_up, flips asset to `on_rent`.
- `rental.order.action_return()` — picked_up→returned, stamps `return_dt_actual`, frees asset, creates inbound picking.
- `rental.order.action_cancel()` — any non-returned state→cancelled, releases asset if it was on rent.
- `rental.order._create_stock_picking(direction)` — internal helper, returns False silently if integration disabled, no `product_id`, or no matching picking type/locations.
- `rental.order._stock_integration_enabled()` — reads `custom_rental.config_stock_integration` ir.config_parameter.
- `rental.order._pdp_audit_classification()` — returns `"financial"` for PDP audit routing.
- `custom.rental.pricing._get_rental_price(product, start_dt, end_dt, currency=None)` (`@api.model`) — quoting helper; accepts `product.product` or `product.template`; greedily fills with largest tier, falls back to smallest tier for leftover hours.
- `custom.rental.pricing._hours()` — converts (duration, unit) → hours via `UNIT_TO_HOURS`.
- Portal: `/my/rentals`, `/my/rentals/<id>`, `/my/rentals/<id>?report_type=pdf`, `/my/rentals/<id>/sign` (JSON).

## Integration Points
- **Depends on:** `custom_core`, `custom_pdp_audit`, `custom_bast`, `mail`, `portal`, `product`, `stock`, `account`.
- **Inherits from:** `product.template` (adds `is_rentable`, `rental_pricing_ids`), `res.config.settings` (adds rental config params), `mail.thread` + `mail.activity.mixin` + `pdp.audited.mixin` (on `rental.order` and `rental.asset`), `portal.CustomerPortal`.
- **Extended by:** typically vertical-specific rental modules (e.g. drone rental, prorata billing variants) — none declared in this manifest but the `line_id` alias in `custom.rental.schedule` is an explicit hook for future multi-line rental.
- **External calls:** none.
- **Cross-vertical:** generic asset-rental capability; not vertical-locked.
- **Account module:** declared as dependency but no `account.move` / invoice generation is implemented here — `total_due` is computed but never posted to accounting.

## Gotchas
- **No invoicing.** `account` is in depends but the module never creates an `account.move`. `total_due` is a display value only. Any BRD requiring rental invoicing needs a new module or extension.
- **Hardcoded 50% late surcharge** in `_compute_fees` (`late_penalty = daily_rate * late_days * 0.5`). Not configurable.
- **Two parallel late-fee mechanisms** that both feed `total_due`: the compute-time `late_penalty` (only relevant after `return_dt_actual` is set) and the cron-time `late_fee_total` (accrues while still `picked_up`). They are additive and can double-charge if both apply post-return — review before relying on either.
- **`UNIT_TO_HOURS` treats a month as 30 days** flat; no calendar-aware month math.
- **`days_planned` / `days_actual` clamp to `max(1.0, ...)`** — a same-day return still bills a full day.
- **Overlap check uses `sudo().search`** and ignores `cancelled`/`returned` orders; multi-company isolation relies on `company_id` being set on records, not on the search domain.
- **Stock picking creation is best-effort and silent**: if no picking type or no `product_id` on the asset, `_create_stock_picking` returns False with no warning. `pickup_picking_id` / `return_picking_id` may stay empty.
- **`rental.order.name` fallback is `"RNT-???"`** if the `rental.order` sequence is missing — this will appear in production data if the sequence XML data file is not loaded.
- **Portal signature endpoint stores raw base64** (strips the `data:image/...;base64,` prefix); validated only with `base64.b64decode(..., validate=True)`, no size/format limit.
- **`custom.rental.schedule` `late` state is view-computed**, not stored on `rental.order` — filters on `rental.order.state` will never see `'late'`.
- **`bast_pickup_id` / `bast_return_id` are M2o but the workflow does not auto-create the BAST** — must be set manually or by an extension.

## Out of Scope
- **Rental invoicing / billing posting** — no `account.move` is created; `total_due` is informational.
- **Deposit handling beyond storage** — `deposit_amount` is captured but never reserved, invoiced, or refunded.
- **Multi-line / multi-asset orders** — one order = one asset. The `line_id` alias in the schedule view hints at future support but is not implemented.
- **Calendar-accurate periods** — month/week conversions are fixed (30/7 days).
- **Maintenance scheduling**
