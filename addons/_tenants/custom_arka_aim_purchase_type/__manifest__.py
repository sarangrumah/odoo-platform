# -*- coding: utf-8 -*-
{
    "name": "ARKA-AIM Trade / Non-Trade Purchases",
    "version": "19.0.1.0.1",
    "summary": "Trade vs Non-Trade purchase stream for ARKA-AIM: own PO numbering, "
    "AP / GR-IR account routing, and Transfer to Asset on a Non-Trade goods receipt.",
    "description": """
ARKA-AIM Trade / Non-Trade Purchases
====================================
Ports the Levi's (``custom_levis_localization``) Trade / Non-Trade split to the
ARKA-AIM tenant and hangs the fixed-asset capitalisation off it.

Purchase type
-------------
``purchase.order.l10n_purchase_type`` (Trade / Non-Trade, default Trade) is picked
by the buyer on the order. It drives:

* **Numbering** -- one monthly-resetting sequence per company AND per stream, on
  top of the tenant's existing ``PO/<CO>/YYYY/MM/NNN`` shape::

      Trade      PO/T/ARKA/2026/09/001     PO/T/AIM/2026/09/001
      Non-Trade  PO/NT/ARKA/2026/09/001    PO/NT/AIM/2026/09/001

  Companies without ``res.company.x_doc_code`` keep core numbering, so the module
  is inert outside the tenant.
* **Account routing** -- the vendor bill inherits the stream and posts its payable
  (payment-term) line to the stream's AP control account, per the editable
  ``arka.purchase.account.map`` table (Accounting > Configuration >
  Trade/Non-Trade Accounts)::

      Trade      2103100001  Trade Payables - Third parties
      Non-Trade  2103300001  Non trade payable - Third parties
                 2103300008  GR/IR clearing - Non Trade Payables - Third Parties
                 6120010001  default expense fallback

  The GR/IR routing on bill *product* lines only fires for PO-linked lines whose
  product category is ``real_time`` valued -- i.e. only where a goods-receipt
  accrual was actually booked. Every ARKA-AIM category is periodic today, so the
  mapping is configured and inert; it starts working the day a category is
  switched to real-time valuation, without a code change.
* **Receipts** -- ``stock.picking.l10n_purchase_type`` is carried from the source
  PO (stored, so it is filterable and groupable).

Transfer to Asset
-----------------
A validated **Non-Trade** goods receipt shows *Convert to Assets* regardless of
how the products are configured: every received line is offered, pre-selected, as
a pooled ``custom.fixed.asset``. Products explicitly flagged on their master
(*Create Fixed Asset on Receipt* / *Is Rental Asset*) keep their own mode --
per-serial conversion still wins where it is configured.

Assets land in **draft** with no acquisition journal, exactly like the existing
ARKA-AIM register: the register is a subledger, the GL was already moved by the
receipt and the vendor bill. Confirm the asset to build its depreciation schedule.

Asset group resolution, in order: wizard override > product's Asset Group >
``res.company.x_nontrade_asset_group_id`` (a per-company default set from
Settings so unflagged opex products convert without touching the master).

TENANT-SCOPED: install only on the ARKA-AIM databases (prd_arkaaim, trn_arkaaim).
""",
    "author": "Platform",
    "website": "https://example.com/custom-platform",
    "category": "Tenants/ARKA-AIM",
    "license": "LGPL-3",
    "depends": [
        "purchase",
        "stock",
        "account",
        "custom_arka_aim_numbering",
        "custom_asset_from_receipt",
    ],
    "capability_tags": ["purchasing", "accounting", "fixed-assets"],
    "data": [
        "security/ir.model.access.csv",
        "views/purchase_account_map_views.xml",
        "views/res_company_views.xml",
        "views/purchase_order_views.xml",
        "views/account_move_views.xml",
        "views/stock_picking_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "auto_install": False,
    "application": False,
}
