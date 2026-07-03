# Levi's Localization (`custom_levis_localization`)

Tenant-scoped module bundling four Levi's requirements. Install only on the
Levi's databases (`prd_levis`, `rnd_levis`, `demo_levis`).

## 1. HS Code on the product master
Depends on native `stock_delivery`, which adds `product.template.hs_code`.
`views/product_template_views.xml` additionally surfaces the field on the
General Information tab (after Category) so it is captured during master-data
entry.

## 2. Receipt qty ≤ demand qty
`models/stock_picking.py` overrides `button_validate`: on any **incoming**
transfer, if a line's done quantity exceeds its demand (ordered) quantity, a
`UserError` is raised listing the offending products. Partial receipts
(done < demand, → backorder) are unaffected.

## 3. No inventory journal at Goods Receipt confirm
`models/stock_move.py` overrides `_should_create_account_move` to return
`False` for vendor goods receipts (moves whose source location usage is
`supplier`). The stock **valuation layer / `stock.move.value`** is still
produced, so on-hand quantity and value stay correct; only the GL
`account.move` at receipt is skipped. Outgoing/COGS, internal transfers,
manufacturing and customer returns keep posting normally.

> **Accounting note:** because the receipt no longer credits the *Stock Interim
> (Received)* account, posting the related vendor bill (anglo-saxon) will leave a
> balance on that interim account. Reconcile inventory value into the GL via a
> periodic manual journal, or revisit this if full perpetual GL is required.

## 4. Payment Voucher & Payment Receipt
`reports/` adds two branded PDF documents on `account.payment`, bound to its
Print menu:
- **Payment Voucher** — vendor / outbound payments.
- **Payment Receipt** — customer / inbound payments.

Both use `web.external_layout` (company letterhead), an amount-in-words line and
prepared/approved/received signature blocks.

## 5. Periodic Inventory Reconciliation
`levis.inventory.reconciliation` (Accounting > Accounting > Inventory
Reconciliation) compares actual on-hand stock value against the GL balance per
valuation account and produces a DRAFT adjustment journal, to compensate for the
suppressed receipt journals (requirement 3). An inactive monthly cron is shipped.

## 6. Receipt lines must come from the PO
`models/stock_move.py` adds an `@api.constrains` on `stock.move`. On a **PO-linked
incoming** transfer, a line is only accepted when it **originates from the
purchase order** (it carries `purchase_line_id`). Any manually added line is
rejected at save time with a `ValidationError`.

- **Strict:** even a manual line for a product that *is* already on the PO is
  rejected — the line must be the one generated from the PO, not a hand-added
  duplicate. This is stronger than a product-membership check.
- Whether a receipt is "PO-linked" is resolved via
  `stock.picking._levis_purchase_orders()` (union of `purchase_id` and each
  move's `purchase_line_id.order_id`, so receipts grouping several POs work).
- **Standalone / non-PO incoming transfers** (no linked purchase order) are
  **not** restricted — there is no PO to check against.
- Enforcement is at save time (not only at validation), matching "cannot be
  added". Requires `purchase_stock` for the `purchase_id` / `purchase_line_id`
  links.
