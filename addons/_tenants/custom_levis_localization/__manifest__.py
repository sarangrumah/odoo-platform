# -*- coding: utf-8 -*-
{
    "name": "Levi's Localization",
    "version": "19.0.1.0.0",
    "summary": "Levi's tenant customisations: HS Code, receipt qty cap, "
    "no inventory GL at goods receipt, payment voucher/receipt.",
    "description": """
Levi's Localization
===================
Bundles four tenant-specific requirements for the Levi's databases
(prd_levis / rnd_levis / demo_levis):

1. **HS Code on the product master.** Pulls in the native ``stock_delivery``
   ``hs_code`` field and additionally surfaces it on the product General
   Information tab so it is filled during master-data entry.

2. **Receipt qty cannot exceed demand.** On any *incoming* transfer the done
   quantity of each line is blocked from exceeding its demand (ordered) quantity
   at validation time.

3. **No inventory journal at Goods Receipt confirm.** For vendor goods receipts
   (moves coming from a supplier location) the automatic stock-valuation
   ``account.move`` is suppressed. The stock valuation layer is still created so
   on-hand value/quantity stay correct; only the GL posting at receipt is
   skipped. Outgoing/COGS and internal moves keep posting normally.

4. **Payment Voucher & Payment Receipt.** Adds two branded PDF documents on
   ``account.payment`` — a *Payment Voucher* for vendor (outbound) payments and
   a *Payment Receipt* for customer (inbound) payments, each with an
   amount-in-words line and prepared/approved/received signature blocks.

5. **Periodic Inventory Reconciliation.** Because receipts/deliveries do not
   post inventory journals in this setup, GL inventory-asset accounts drift from
   the real on-hand value. ``levis.inventory.reconciliation`` (Accounting >
   Accounting > Inventory Reconciliation) computes, per valuation account, the
   actual stock value (``stock.quant.value``) vs the GL balance and generates a
   DRAFT adjustment journal for review. An inactive monthly cron is provided.

TENANT-SCOPED: install only on the Levi's tenant databases.
""",
    "author": "Custom Platform",
    "website": "https://example.com/custom-platform",
    "category": "Tenants/Levis",
    "license": "LGPL-3",
    "depends": [
        "product",
        "stock",
        "stock_account",
        "stock_delivery",
        "purchase",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/inventory_reconciliation_data.xml",
        "views/product_template_views.xml",
        "views/inventory_reconciliation_views.xml",
        "reports/paperformat.xml",
        "reports/payment_report_actions.xml",
        "reports/payment_voucher_templates.xml",
        "reports/payment_receipt_templates.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
