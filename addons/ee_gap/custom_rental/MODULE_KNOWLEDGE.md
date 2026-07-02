---
status: draft
generated_at: 2026-07-02T08:10:48Z
generator: bootstrap-v1
module: custom_rental
manifest_version: 19.0.0.3.0
---

# custom_rental

## Purpose
This module manages the lifecycle of asset rentals, including pricing tiers, scheduling, billing, and customer portal access. It ensures that rental orders are properly created, tracked, and invoiced while providing a user-friendly interface for customers to view their rental history.

## Business Flow
1. **Customer Places an Order:**
   - A customer creates a new `rental.order` by selecting an asset or product.
   - The order details include the pickup date (`pickup_dt`), expected return date (`return_dt_expected`), and quantity of assets to rent.
   
2. **Order Confirmation:**
   - Upon confirmation, the state changes from `draft` to `confirmed`.
   - A stock picking is created if configured (depends on `custom_rental.config_stock_integration`).

3. **Asset Pickup:**
   - The asset is marked as `on_rent`, and a BAST document may be generated for pickup.
   
4. **Return of Asset:**
   - Upon return, the state changes to `returned`.
   - A BAST document may be generated for return.
   - Late fees are accrued based on the number of overdue days.

5. **Late Fee Accrual:**
   - A cron job runs daily to accrue late fees (`custom.rental.late.fee.line`).
   
6. **Customer Portal Access:**
   - Customers can view their rental history and details via the customer portal.
   - They can sign the rental contract.

## Key Models
- `rental.order` — Top-level rental agreement; holds partner, asset/product, quantity, pickup/return dates, late fees.
  - Fields:
    - `partner_id`: Partner who placed the order.
    - `asset_id`: Asset being rented (single-serial mode).
    - `product_id`: Product for bulk rentals.
    - `pickup_dt`: Date and time when the asset is picked up.
    - `return_dt_expected`: Expected return date and time.
    - `daily_rate`: Daily rental rate.
    - `late_fee_rate`: Late fee percentage per day.

- `custom.rental.pricing` — Per-period rental pricing tier attached to product.template.
  - Fields:
    - `name`: Name of the pricing tier.
    - `product_template_id`: Product template that this pricing applies to.
    - `duration`: Duration in hours for which the price is valid.
    - `price`: Price per duration.

- `custom.rental.schedule` — SQL view aggregating rental.order into a calendar-friendly schedule.
  - Fields:
    - `name`: Name of the order.
    - `order_id`: Reference to the rental.order record.
    - `asset_id`: Asset being rented.
    - `partner_id`: Partner who placed the order.
    - `date_start`: Pickup date and time.
    - `date_stop`: Expected return date and time.

## Important Fields
- `rental.order.state` (Selection: draft/confirmed/picked_up/returned/cancelled): Tracks the lifecycle state of the rental order.
- `custom.rental.pricing.duration` (Integer): Defines the duration in hours for which the price is valid.
- `custom.rental.schedule.date_start` (Datetime): Marks the start date and time of the rental period.

## Public Methods
- `rental.order.action_confirm()`: Confirms a draft order, setting its state to `confirmed`.
- `custom.rental.pricing._get_rental_price(start_dt, end_dt)`: Computes the total price for a given duration based on active pricing tiers.

## Integration Points
- **Depends on:** custom_core, custom_pdp_audit, custom_bast, mail, portal, product, stock, account.
- **Inherits from:** `stock.move` (adds `is_loan` field).
- **Extended by:** None.
- **External calls:** None.
- **Cross-vertical:** Deployed in arkaim, jds, ppob.

## Gotchas
- The late fee accrual mechanism relies on a daily cron job. Ensure this is configured and running.
- The internal asset loan mode requires an `on_loan_location_id` to be set for the rental asset.

## Out of Scope
- Multi-line rentals: Currently, each order represents a single line item. Future enhancements may support multi-line orders.
- Customizable pricing tiers by customer segment or time of day: This module uses fixed pricing tiers defined in product templates.
- Detailed stock management beyond basic pickings: While stock pickings are generated for outbound and inbound movements, advanced stock tracking features are not integrated.
