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
