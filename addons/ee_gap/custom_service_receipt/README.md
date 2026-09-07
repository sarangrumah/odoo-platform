# Custom Service Receipt

Receive purchased **services** on a goods receipt, so the vendor bill is backed by
an acceptance document.

## The problem

Odoo never puts a service on a receipt. `purchase_stock` filters every picking
path on `product_id.type == 'consu'`, so a purchased service can only have its
received quantity typed by hand on the purchase order line — and where the
product bills on *ordered* quantities, not even that.

The result, seen on a live database:

```
PO/AIM/2026/08/002   Etiqa Insurance   qty_received 0.00   qty_invoiced 1.00
```

A bill exists; nothing records that the service was ever delivered.

## What this does

Tick **Receive on Goods Receipt** on the service product (Purchase tab). From
then on:

- the service is pushed onto the purchase order's receipt, alongside any goods;
- an order made only of services gets a receipt too, which core would skip;
- the move is available immediately — a service is never reserved;
- validating the receipt drives `qty_received`, which drives what can be billed;
- three-way match and receipt-date reporting start working for services.

Ticking the flag also switches the control policy to **On received quantities**.
A receipt that does not gate the bill would be decoration.

## What it deliberately does not do

- **No inventory or accounting side effects.** A service creates no quant, no
  valuation layer and no journal entry — `stock_account` values only storable,
  real-time products. The gain here is control and traceability, not accrual. If
  you want an expense accrual at acceptance, that is separate work.
- **It does not change the product type.** Services stay services, because
  `custom_coretax_export` reads `product.type` to fill the e-Faktur
  `BARANG_JASA` column.
- **It does not retro-fit confirmed orders.** Flag the product, then confirm new
  orders.

## Install

```
depends: purchase_stock
```

Inert until a product is flagged, so it is safe to install on any database.
