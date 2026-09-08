# -*- coding: utf-8 -*-
{
    "name": "ARKA Show Date",
    "version": "19.0.1.10.0",
    "summary": "Show-date and event on the whole sale-to-purchase chain, one "
    "analytic account per event, and a PO raised on the sister company "
    "straight from the sale. PT ARKA / AIM only.",
    "description": """
ARKA Show Date
==============
Adds a 'Show Date' (``x_custom_show_date``) Date field captured on the
Quotation (``sale.order``), carried to the Sales Order, and propagated to the
Customer Invoice (``account.move``, ``out_invoice``). For companies that opt in
via ``res.company.x_custom_show_date_enabled``, the customer-invoice
payment-term due dates (``date_maturity``) are anchored to the Show Date instead
of the invoice date (i.e. "X days after show date").

Event description block
-----------------------
The same opt-in also captures ``x_custom_event_name``,
``x_custom_event_location`` and ``x_custom_dp_note`` on the order, and appends
them (with the show date, ``dd.mm.yy``) as a second line under every product
line's description::

    Jasa Drone Show 250 unit
    Event Danone, Lokasi Taman Bhagawan Bali, 07.08.26, DP 50%

The description is a stored compute with ``readonly=False``, so the block is
rebuilt whenever the event data changes but manual edits survive in between. It
travels to the customer invoice through the standard ``_prepare_invoice_line``.
The down-payment line carries the same event data in its own one-line form
(see below).

Down-payment line description
-----------------------------
Core labels the down-payment invoice line ``Down payment of 50.00%``, and that
wording is what the customer sees on the invoice PDF *and* in the Faktur Pajak
"Nama Barang Jasa" cell — ``custom_coretax_export`` reads
``line.product_id.name or line.name``, and a DP line carries no product, so it
falls through to the name. For flagged companies the line is relabelled with the
products being down-paid followed by the event detail instead::

    Jasa Drone Show 250 Unit, Biaya Luar Kota, Event Danone,
    Lokasi Taman Bhagawan Bali, 07.08.26 (Uang Muka 50%)

Rewriting the stored ``name`` fixes both printouts from one place;
``custom_report_templates`` and ``custom_coretax_export`` are shared addons and
stay untouched. The string is deliberately kept to a single line because it
lands in one cell of the coretax import file. A fixed-amount down payment gets
``(Uang Muka)`` with no percentage, and ``x_custom_dp_note`` is left out of this
line because the trailing marker already states the down payment. The journal item carries the same label; the
down payment stays identifiable in the GL through account 2108100001 and the
order's "Down Payments" section.

Settlement (pelunasan) deduction line
-------------------------------------
The deduction line on the settlement invoice is labelled by core
``sale.order.line._get_downpayment_description()`` as ``Down Payment (ref: INV/…
on 08/14/2026)``, and that string reaches the order's "Down Payments" section,
the settlement invoice PDF and the settlement's Faktur Pajak alike. For flagged
companies it becomes the same product + event wording, with the core reference
kept as the trailing marker so Finance can still tie the deduction back to the
down-payment invoice::

    Jasa Drone Show 1000 Unit, Event Soekarno Cup, Lokasi Stadion Gelora Bung
    Tomo Surabaya, 24.08.26 (Uang Muka ref: INV/ARKA/2026/08/002 tgl 14/08/2026)

Event on the buying leg
-----------------------
The purchase order captures the same ``x_custom_show_date`` /
``x_custom_event_name`` / ``x_custom_event_location``, hands them to the vendor
bill through ``_prepare_invoice``, and — where
``custom_intercompany_procurement`` mirrors the PO into the sister company —
writes them onto the mirrored sales order. Before this the event reached the
selling company only as free text in the header note ("MERDEKA RUN - MONAS"),
so it could not be reported on and could not be trusted.

Purchase order raised from the sale
-----------------------------------
``sale.order.action_custom_create_ic_purchase_order()`` creates a DRAFT purchase
order on the sister company named by the intercompany rule, carrying the event,
the show date and the ordered lines. Prices are left to the vendor's own supplier
info rather than copied from the customer order — the sister company's price is
not the customer's price. Confirming the draft then triggers the existing PO ->
SO mirror, so one sale produces the whole chain: ARKA sale -> ARKA purchase ->
AIM sale, all naming the same event.

Sale product vs purchase product
--------------------------------
The client keeps two catalogues for one show: the customer order carries the
*Jasa* product ARKA sells, the purchase order on AIM carries the matching *Sewa*
rental. ``product.template.x_custom_ic_purchase_product_id`` ("Purchased As")
records that pairing, and the generated purchase order swaps the product::

    Jasa Drone Show 250 Unit  (sold)  ->  Sewa Drone Show 250 Unit  (bought)

Odoo has no native sale-to-purchase substitution — ``product.supplierinfo``
prices a product from a vendor, it does not replace it. Resolution is one hop
only and falls back to the product itself, so an unpaired product still buys as
itself.

Analytic account per event
--------------------------
For companies with ``res.company.x_custom_event_tracking_enabled``, sales
orders, purchase orders and journal entries resolve their event to a single
analytic account in the "Event" plan, named by concatenating the event, its
location and the show date::

    Soekarno Cup - Stadion Gelora Bung Tomo Surabaya - 24.08.26

The account is created on first use, matched on a normalised key so retyped
spacing and capitalisation still land on one account, and is created WITHOUT a
company so ARKA's revenue and AIM's cost for the same show meet on it — which is
what makes a cross-company Profit & Loss per event possible. Order confirmation
stamps the distribution on lines that carry none; a "Tag Event" button does the
same for a bill that has no source document. Lines an operator has already
split across events by hand are never overwritten.

This gate is deliberately NOT ``x_custom_show_date_enabled``: that flag makes
the show date required on sales orders and re-anchors customer-invoice due
dates, so enabling it on AIM would block AIM orders that have no show. Event
tracking makes nothing required and moves no due date, so it is safe on both
sister companies.

Overhead allocation
-------------------
Payroll, tax, insurance and the general journal belong to no single show, so
they sit in the Unassigned column and make every event look better than it was.
``custom.arka.event.allocation`` lets the client write the rule down — period,
which journals and accounts count as overhead, and whether the split follows
event revenue, directly attributed cost, equal shares, or percentages typed by
hand — then compute it, read it, and apply it.

The split is written as an ``analytic_distribution`` carrying a percentage per
event, which the Profit & Loss per Event already weights by. No amount moves, no
account changes, nothing is re-posted. Lines a document already attributed are
never touched, only posted expense lines are eligible, and every line written
carries ``x_custom_event_allocation_id`` so Reset puts back exactly what that run
changed.

TENANT-SCOPED: built for the PT ARKA company on the aimarka tenant DBs
(uat_aimarka, rnd_aimarka, prd_EAL_ArkaAim). The behaviour is gated by the
``res.company`` boolean flag, NOT by company name and NOT merely by install, so
the module is safe to install on a multi-company DB (e.g. AIM + ARKA): only the
company with the flag ticked (PT ARKA) is affected. Until the flag is ticked the
module is inert.
""",
    "author": "Platform",
    "website": "https://example.com/custom-platform",
    "category": "Tenants/ARKA-AIM",
    "depends": [
        "sale_management",
        "purchase",
        "account",
        "analytic",
        "custom_core",
        "custom_accounting_reports",
        # The SO -> PO button and the event carry-over into the sister
        # company's mirrored order both build on this module's
        # account.intercompany.rule and its PO -> SO mirror.
        "custom_intercompany_procurement",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/analytic_plan.xml",
        "data/config_parameters.xml",
        "views/res_company_views.xml",
        "views/sale_order_views.xml",
        "views/product_views.xml",
        "views/purchase_order_views.xml",
        "views/account_move_views.xml",
        "views/event_allocation_views.xml",
        "views/profit_loss_wizard_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
    "license": "LGPL-3",
}
