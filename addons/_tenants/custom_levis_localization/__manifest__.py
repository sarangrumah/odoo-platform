# -*- coding: utf-8 -*-
{
    "name": "Levi's Localization",
    "version": "19.0.1.29.0",
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

12. **Periodic COGS per Operating Unit.** Levi's imports its POS backlog long
    before the purchase data exists, so at the moment of sale no unit cost is
    known. Odoo 19 cannot fix that later — ``stock.move.value`` is written once at
    ``_action_done`` and the ``_run_fifo_vacuum`` that used to revalue past
    outgoing moves is gone, so a sale made against empty stock stays valued at
    zero forever. ``levis.cogs.run`` (Accounting > Accounting > Periodic COGS)
    therefore recognises COGS *periodically*: once the purchases are in and each
    product carries a cost, it multiplies the quantity sold at each store by that
    cost, aggregates per (Operating Unit, product category), and generates a DRAFT
    Dr COGS-<category> / Cr Inventories-<category> entry with the store's OU
    analytic on both legs. Quantities whose product still has no cost are counted
    and shown rather than silently contributing zero. No stock moves are created,
    so the X20 on-hand snapshot stays intact.

13. **Indonesian bank master data.** ``res.bank`` gains ``l10n_id_bi_code``
    (*Kode BI*) — the 7-digit Bank Indonesia clearing/RTGS participant code, or
    *sandi bank* — shown on the bank form/list and searchable. The module seeds 181
    banks (name + SWIFT/BIC + Kode BI) from ``data/res.bank.csv``. Kode BI is the
    unique key: BIC cannot be, since every BI branch office shares ``INDOIDJA``.
    Feeds the *Acquiring Bank* on the Card BIN / MDR mapping above.

15. **Monthly POS Clearing.** ``levis.pos.clearing`` (Accounting > Accounting >
    POS Clearing) settles the per-tender POS receivables (``1106000101``..``110``)
    against the bank settlements already imported, replacing three host scripts
    that were hardcoded to one month and driven by a client workbook.

    It needs no upload: the acquirer already prints the gross and its fee on every
    settlement narrative (``TGH``/``DDR``, ``TGH``/``ADM``, ``QR``/``DDR``,
    ``AMT``/``MDR``), so the fee is exact per settlement instead of a monthly
    figure spread pro-rata. Which tender account a settlement pays cannot be read
    anywhere — one card MID covers Visa, Mastercard, JCB and Amex alike — so it is
    discovered by consuming that store's open receivable debits for the trading
    day, largest residual first, and whatever is left over is reported as a
    shortfall rather than forced somewhere.

    Three stages, deliberately separate: **Compute** builds the summary and
    creates nothing at all; **Generate Draft Entries** writes DRAFT entries
    carrying the store's Operating-Unit analytic on every leg; **Post &
    Reconcile** posts them and reconciles each credit leg with exactly the
    receivable lines its allocation names (not a blanket per-account sweep, so
    per-store residuals stay readable afterwards). There is no cron and no
    auto-post.

    Supporting records: ``levis.clearing.config`` (Configuration > POS Clearing
    Accounts, seeded by account code) and ``levis.bank.mid.map`` (Configuration >
    Bank MID Mapping), because bank narratives truncate store names inconsistently
    and only the merchant/terminal number is a safe key. A wizard scans a period
    and lists what is still unmapped, biggest amount first. Unparsed narratives,
    unmapped terminals, amount mismatches, statement days missing from the import
    and posted receivables lacking an Operating Unit are all surfaced as
    diagnostics with click-through, and block generation until acknowledged.

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
        "point_of_sale",
        "custom_retail_import_pos",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/res.bank.csv",
        "data/config_parameters.xml",
        "data/po_sequences.xml",
        "data/bill_sequences.xml",
        "data/payment_methods.xml",
        "data/scrap_batch_sequence.xml",
        "data/inventory_reconciliation_data.xml",
        "data/cogs_run_data.xml",
        "data/categ_reclass_sequence.xml",
        "data/pos_clearing_data.xml",
        "views/res_bank_views.xml",
        "views/product_template_views.xml",
        "views/product_product_views.xml",
        "views/inventory_reconciliation_views.xml",
        "views/cogs_run_views.xml",
        "views/categ_reclass_views.xml",
        "views/levis_clearing_config_views.xml",
        "wizard/levis_bank_mid_map_wizard_views.xml",
        "views/levis_pos_clearing_views.xml",
        "views/account_bank_statement_line_views.xml",
        "views/scrap_batch_views.xml",
        "views/levis_mdr_bin_views.xml",
        "views/account_account_views.xml",
        "views/account_payment_register_views.xml",
        "views/account_payment_views.xml",
        "views/account_move_views.xml",
        "views/stock_report_action.xml",
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
