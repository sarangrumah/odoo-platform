# -*- coding: utf-8 -*-
{
    "name": "Custom Rental — Sales Bridge",
    "summary": "Dispatch the units behind a sales order and reconcile what comes back, "
    "without moving the commercial document off Sales",
    "description": """
Custom Rental — Sales Bridge
============================

The problem this solves is a mismatch of shape. ARKA-AIM sells drone shows: one
sales-order line, ``Jasa Drone Show 1500 Unit``, quantity 1, priced as a lump sum
for the event. ``rental.order`` prices by ``daily_rate x days x qty`` and accrues
a daily late fee. Moving the selling onto the rental module would mean rebuilding
a commercial process that already works, on a pricing model that does not fit.

So the sales order stays the commercial document and the source of revenue, and
this module borrows from rental only the part Sales cannot do: knowing which
physical units went out to an event and what came back.

Nothing changes for the seller
------------------------------

Quotation, show date, event name, BAST, numbering, down payments, tax --
untouched. One smart button appears on the order. The people who use the
deployment screen are Ops and the warehouse, not Sales, and a company that is not
ready can leave ``deployment_auto_create`` off and carry on exactly as today.

The deployment document
-----------------------

Confirming a sales order that names a deployment product creates one
``rental.order`` in **internal-loan** mode: units move Stock -> On-Loan inside
the company's own location tree, never to a customer location, so no COGS and no
valuation journal can result. ``daily_rate`` is zero and invoicing from the
rental side is refused outright -- the money is on the sales order, and a second
document that could also bill it is a liability, not a feature.

Where a rented product carries a phantom BOM, ``custom_rental_bom_explosion``
turns the qty-1 bundle into one stock move per component, so a 1,500-drone show
really moves 1,500 serials plus batteries and controllers. That module is
optional; without it a deployment moves the product itself.

Reconciling the return
----------------------

``custom_rental._check_returned_serials`` already compares the serials that went
out against the serials that came back, and refuses to close the order when they
disagree. What it did with that knowledge was raise an error listing the missing
ones, which leaves the operator with an accurate complaint and nowhere to go --
in practice, an inventory adjustment that hides the loss.

This turns that dead end into a reconciliation step. Each serial that did not
come back is proposed as **missing**; any serial that came back broken can be
marked **damaged**. Confirming hands both sets to ``custom_asset_lifecycle``,
which writes the condition, moves the serial to the lost or damage warehouse,
opens repair orders, and records it all against the unit's history.

That closes the loop the register was missing: an event ends, and the units that
did not survive it are already cases on the asset register rather than a
discrepancy somebody has to notice.
""",
    "author": "Custom Platform",
    "category": "Sales/Rental",
    "version": "19.0.1.1.0",
    "license": "LGPL-3",
    "depends": [
        "sale",
        "custom_rental",
        "custom_asset_lifecycle",
    ],
    "capability_tags": ["rental", "sales", "fixed-assets", "audit-trail"],
    "data": [
        "security/ir.model.access.csv",
        "views/rental_order_views.xml",
        "views/sale_order_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/deployment_return_reconcile_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
