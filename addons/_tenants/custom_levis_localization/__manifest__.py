# -*- coding: utf-8 -*-
{
    "name": "Levi's Localization",
    "version": "19.0.1.12.1",
    "summary": "Levi's tenant customisations: HS Code, receipt qty cap, "
    "no inventory GL at goods receipt, payment voucher/receipt, journal billing, "
    "multi-COA admin fees on payment.",
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

3. **Goods-Receipt GL mode (switchable).** Controlled by the system parameter
   ``custom_levis_localization.suppress_gr_journal``:
   * ``0`` (default) — **Automated valuation**: the stock-valuation
     ``account.move`` posts normally at receipt confirm
     (Dr Inventory / Cr Stock Input / GRIR).
   * ``1`` — **Periodic**: for vendor goods receipts (moves from a supplier
     location) the GR ``account.move`` is suppressed (the stock valuation layer
     is still created so on-hand value/qty stay correct); the GL is realigned
     via the Inventory Reconciliation tool below. Outgoing/COGS and internal
     moves keep posting normally in both modes.

4. **Payment Voucher & Payment Receipt.** Adds two branded PDF documents on
   ``account.payment`` — a *Payment Voucher* for vendor (outbound) payments and
   a *Payment Receipt* for customer (inbound) payments. Each renders the
   payment's own journal entry as a COA / DEBIT / CREDIT table (with the
   reconciled AP document and vendor invoice ref per line), an Indonesian
   amount-in-words (*Terbilang*) line, the recipient bank block and a
   prepared/checked/approved/received signature strip.

7. **Journal Billing.** A per-move printout on ``account.move`` (bound to the
   Print menu) rendering a posted vendor bill as a GL voucher: a two-column
   meta header (Reference / Invoice AP / dates / *Terbilang*; Vendor / PO / Tax
   Number / Tax Date) and a GL table (GL account, description, operating unit,
   line description, debit, credit) with a TOTAL row and Posted/Approved
   signatures. Optional-field lookups (l10n_id tax number, analytic "operating
   unit", linked PO) degrade gracefully when the source module is absent.

10. **Scrap Batch (multiple products).** ``custom.scrap.batch`` (Inventory >
   Operations > Scrap Batches) scraps several products in one action: each line
   drives a real ``stock.scrap`` (on-hand qty + stock valuation layer stay
   correct) and, on validation, ONE consolidated ``account.move`` is posted —
   Dr Scrap Loss (P&L) / Cr Stock Valuation grouped per product category. The
   scrap-loss account code comes from the system parameter
   ``custom_levis_localization.scrap_loss_account_code``; the store's
   Operating-Unit analytic is stamped on every line; the entry is idempotent
   (``ref`` ``SCRAP-VAL:<id>`` + stored ``move_id``). Real-time categories only.

11. **Card BIN / MDR configuration.** ``levis.mdr.bin`` (Accounting >
   Configuration > Card BIN / MDR) maps card BIN ranges to an acquiring bank, an
   MDR rate (percent + optional fixed fee) and an MDR expense account, with
   effective dating. On an inbound customer card receipt, entering the *Card BIN*
   on Register Payment resolves the mapping and nets the MDR off the settlement
   via the admin-fee channel: Dr Bank (net) / Dr MDR expense / Cr Receivable, the
   receivable still reconciling in full.

5. **Periodic Inventory Reconciliation.** Because receipts/deliveries do not
   post inventory journals in this setup, GL inventory-asset accounts drift from
   the real on-hand value. ``levis.inventory.reconciliation`` (Accounting >
   Accounting > Inventory Reconciliation) computes, per valuation account, the
   actual stock value (``stock.quant.value``) vs the GL balance and generates a
   DRAFT adjustment journal for review. An inactive monthly cron is provided.

6. **Receipt lines must come from the PO.** On a PO-linked *incoming* transfer
   only lines that originate from the purchase order (carrying
   ``purchase_line_id``) may be received. Any manually added line -- even for a
   product already on the PO -- is rejected the moment it is saved
   (``ValidationError``). Standalone (non-PO) incoming transfers are unaffected.

8. **Multi-COA admin fees on payment.** The Register Payment wizard gains an
   *Admin Fees* section where one or more fee lines (each with its own COA and
   amount) can be added on top of the bill. The payment total becomes
   ``bill residual + Sum(fees)``; each fee posts to its own account while the
   bill still reconciles in full. Fees ride the native write-off channel, so
   they also appear as journal items on the Payment Voucher/Receipt.

9. **Trade / Non-Trade split + Operating-Unit dimension.** The purchase order
   gains a ``Purchase Type`` (Trade / Non-Trade) that drives:
   * **Numbering** — separate monthly-reset sequences
     ``PO/T/EBR/YYYY/MM/#####`` (trade) and ``PO/NT/EBR/YYYY/MM/#####``
     (non-trade).
   * **COA mapping** (``levis.purchase.account.map``) — the vendor-bill payable
     account (Trade Payables vs Non-Trade payable) and, for storable lines, the
     GR/IR clearing account used by the goods-receipt valuation journal.
   Each store (``stock.warehouse``) becomes a posted **Operating Unit**: it owns
   an analytic account (in the "Operating Unit" plan) stamped on every PO / bill
   / GR-journal line, and a dedicated **purchase journal** so bills, journals
   and P&L separate per store. Provisioned idempotently by the module
   ``post_init_hook`` (fresh installs) or ``scripts/tenants/levis/40_setup_trade_ou.py``
   (already-installed DBs).

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
        "purchase_stock",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/config_parameters.xml",
        "data/po_sequences.xml",
        "data/bill_sequences.xml",
        "data/payment_methods.xml",
        "data/scrap_batch_sequence.xml",
        "data/inventory_reconciliation_data.xml",
        "views/product_template_views.xml",
        "views/inventory_reconciliation_views.xml",
        "views/scrap_batch_views.xml",
        "views/levis_mdr_bin_views.xml",
        "views/account_payment_register_views.xml",
        "views/purchase_order_views.xml",
        "views/levis_purchase_account_map_views.xml",
        "reports/paperformat.xml",
        "reports/payment_report_actions.xml",
        "reports/payment_voucher_templates.xml",
        "reports/payment_receipt_templates.xml",
        "reports/journal_billing_templates.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "auto_install": False,
    "application": False,
}
