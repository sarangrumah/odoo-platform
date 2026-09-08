# -*- coding: utf-8 -*-
"""A deployment is a rental order that carries no money and answers to a sale.

Two things make it different from an ordinary rental, and both are guards rather
than features:

* it cannot be invoiced -- the sales order already bills the event, and a second
  document able to bill the same thing is how customers get charged twice;
* a serial mismatch on return opens a reconciliation instead of a dead end.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RentalOrder(models.Model):
    _inherit = "rental.order"

    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sales Order",
        copy=False,
        index=True,
        ondelete="set null",
        help="The commercial document behind this dispatch. Set means this is a "
        "deployment: the money lives on the sale, never here.",
    )
    is_deployment = fields.Boolean(
        compute="_compute_is_deployment",
        store=True,
        index=True,
    )
    sale_client_ref = fields.Char(related="sale_order_id.client_order_ref", string="Customer Reference", readonly=True)

    @api.depends("sale_order_id")
    def _compute_is_deployment(self):
        for order in self:
            order.is_deployment = bool(order.sale_order_id)

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------
    @api.constrains("sale_order_id", "daily_rate", "deposit_amount")
    def _check_deployment_carries_no_money(self):
        for order in self:
            if not order.sale_order_id:
                continue
            if order.daily_rate or order.deposit_amount:
                raise UserError(
                    _(
                        "Deployment %(name)s answers to sales order %(order)s, which "
                        "is what bills the customer. Its own daily rate and deposit "
                        "must stay zero.",
                        name=order.name,
                        order=order.sale_order_id.name,
                    )
                )

    def action_create_invoice(self):
        """Refuse outright rather than quietly producing a second bill.

        ``custom_rental_invoicing``'s auto-invoice-on-return catches UserError and
        notes it on the order, so a deployment that reaches that path leaves a
        trail instead of an invoice -- which is the outcome we want.
        """
        deployments = self.filtered("sale_order_id")
        if deployments:
            raise UserError(
                _(
                    "These are deployments, billed through their sales orders: "
                    "%(names)s. Invoice the sales order instead.",
                    names=", ".join("%s -> %s" % (d.name, d.sale_order_id.name) for d in deployments),
                )
            )
        # Defined here even when custom_rental_invoicing is absent, so check
        # rather than assume there is a parent implementation to call.
        parent = getattr(super(), "action_create_invoice", None)
        if parent is None:
            raise UserError(_("Rental invoicing is not installed on this database."))
        return parent()

    # ------------------------------------------------------------------
    # Return reconciliation
    # ------------------------------------------------------------------
    def _returned_serial_discrepancy(self):
        """(dispatched-but-not-returned, returned-but-not-dispatched) as lots."""
        self.ensure_one()
        Lot = self.env["stock.lot"]
        if not (self.pickup_picking_id and self.return_picking_id):
            return Lot, Lot
        out = self.pickup_picking_id.move_line_ids.lot_id
        back = self.return_picking_id.move_line_ids.lot_id
        if not out:
            return Lot, Lot
        return out - back, back - out

    def action_open_return_reconcile_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Reconcile Return of %s", self.name),
            "res_model": "custom.rental.return.reconcile.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_rental_order_id": self.id},
        }

    def action_validate_loan_return(self):
        """Send a serial mismatch to the reconciliation wizard, not to a dead end.

        ``custom_rental`` raises here listing the serials that did not come back,
        which is accurate and useless: the operator is told to "resolve via
        inventory adjustment or pursue claim", and an inventory adjustment is
        exactly how a lost drone stops being anybody's problem. Where the units
        are fixed assets we can do better -- book them as missing or damaged
        against the register.
        """
        redirect = self.env["rental.order"]
        for order in self:
            missing, unexpected = order._returned_serial_discrepancy()
            if (missing or unexpected) and order._reconcilable_lots(missing | unexpected):
                redirect |= order
        if redirect:
            if len(redirect) > 1:
                raise UserError(
                    _(
                        "Reconcile these returns one at a time -- each one books "
                        "conditions against the asset register: %(names)s",
                        names=", ".join(redirect.mapped("name")),
                    )
                )
            return redirect.action_open_return_reconcile_wizard()
        return super().action_validate_loan_return()

    def _reconcilable_lots(self, lots):
        """Only take over when the serials are fixed assets we can actually book.

        A mismatch on serials that are not in the register is still a real
        problem, and the original hard error is the right answer for it.
        """
        if not lots:
            return self.env["custom.fixed.asset"]
        return self.env["custom.fixed.asset"].sudo().search([("lot_id", "in", lots.ids)])

    # ------------------------------------------------------------------
    # Dispatch from where the units actually are
    # ------------------------------------------------------------------
    def _deployment_source_location(self):
        """The location a deployment picks from.

        ``custom_rental`` sources an internal loan from the *first* internal
        picking type's ``default_location_src_id``. In a multi-step warehouse
        that is the Input dock, and in ARKA-AIM's it is not where the fleet
        lives. Reserving from a location the units are not in does not fail --
        it books a negative quant at the source, a positive one at the
        destination, and leaves the original stock untouched. The unit is now in
        two places, silently. That is precisely the pattern that had 2,572 units
        reporting the wrong warehouse.

        ``custom_asset_stock_link`` already corrects this for single-serial
        rentals by reading the asset's own position. A deployment is bulk mode --
        one bundle standing for hundreds of serials -- so there is no single
        asset to ask, and the fix has to come from configuration instead.
        """
        self.ensure_one()
        configured = self.company_id.deployment_source_location_id
        if configured:
            return configured
        warehouse = self.on_loan_location_id.warehouse_id
        return warehouse.lot_stock_id if warehouse else self.env["stock.location"]

    def _resolve_picking_type_and_locations(self, direction):
        ptype, loc_src, loc_dst = super()._resolve_picking_type_and_locations(direction)
        if not self.sale_order_id or not self.is_internal_loan:
            return ptype, loc_src, loc_dst
        source = self._deployment_source_location()
        on_loan = self.on_loan_location_id
        if not source or not on_loan:
            return ptype, loc_src, loc_dst
        warehouse = on_loan.warehouse_id or source.warehouse_id
        ptype = (warehouse.int_type_id if warehouse else False) or ptype
        if direction == "outgoing":
            return ptype, source, on_loan
        return ptype, on_loan, source
