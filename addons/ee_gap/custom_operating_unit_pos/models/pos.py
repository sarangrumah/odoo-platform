# -*- coding: utf-8 -*-
"""Operating Unit on the point of sale.

A POS belongs to exactly one store, so the whole chain is derivable from
``pos.config.warehouse_id``: the config's unit, the sessions opened on it, the
orders rung up in them, and every line of the closing entry.

The closing entry is stamped line by line rather than left to the move → line
inheritance. Core builds that move on the POS journal, which is usually a
company-wide journal with no unit of its own, so the move itself has nothing to
inherit from; and the lines core produces (sale, tax, receivable) each go
through their own vals hook. This mirrors what ``custom_levis_localization``
already does for the analytic leg of the same dimension — on a Levi's database
both are stamped, by the two modules, on the same lines.
"""

from odoo import api, fields, models


class PosConfig(models.Model):
    _name = "pos.config"
    _inherit = ["pos.config", "operating.unit.mixin"]

    operating_unit_id = fields.Many2one(compute="_compute_operating_unit_id", store=True, readonly=False)

    @api.depends("warehouse_id")
    def _compute_operating_unit_id(self):
        index = self.env["operating.unit"]._warehouse_index()
        for config in self:
            if config.operating_unit_id:
                continue
            config.operating_unit_id = index.get(config.warehouse_id.id) or False


class PosSession(models.Model):
    _name = "pos.session"
    _inherit = ["pos.session", "operating.unit.mixin"]

    operating_unit_id = fields.Many2one(related="config_id.operating_unit_id", store=True, readonly=True, index=True)

    def _create_account_move(self, *args, **kwargs):
        move = super()._create_account_move(*args, **kwargs)
        # The move is created on the POS journal, which carries no unit of its
        # own; give it the session's so the entry is addressable as a whole.
        if self.operating_unit_id and self.move_id and not self.move_id.operating_unit_id:
            self.move_id.with_context(ou_skip_check=True).operating_unit_id = self.operating_unit_id.id
        return move

    def _ou_stamp(self, vals):
        """Put this session's unit on one closing-entry line's vals."""
        if vals and self.operating_unit_id:
            vals["operating_unit_id"] = self.operating_unit_id.id
        return vals

    def _get_sale_vals(self, key, *args, **kwargs):
        return self._ou_stamp(super()._get_sale_vals(key, *args, **kwargs))

    def _get_tax_vals(self, *args, **kwargs):
        return self._ou_stamp(super()._get_tax_vals(*args, **kwargs))

    def _get_combine_receivable_vals(self, *args, **kwargs):
        return self._ou_stamp(super()._get_combine_receivable_vals(*args, **kwargs))

    def _get_split_receivable_vals(self, *args, **kwargs):
        return self._ou_stamp(super()._get_split_receivable_vals(*args, **kwargs))

    def _get_invoice_receivable_vals(self, *args, **kwargs):
        return self._ou_stamp(super()._get_invoice_receivable_vals(*args, **kwargs))

    def _get_stock_expense_vals(self, *args, **kwargs):
        return self._ou_stamp(super()._get_stock_expense_vals(*args, **kwargs))


class PosOrder(models.Model):
    _name = "pos.order"
    _inherit = ["pos.order", "operating.unit.mixin"]

    operating_unit_id = fields.Many2one(compute="_compute_operating_unit_id", store=True, readonly=False, index=True)

    @api.depends("session_id.operating_unit_id", "config_id.operating_unit_id")
    def _compute_operating_unit_id(self):
        for order in self:
            if order.operating_unit_id:
                continue
            order.operating_unit_id = (
                order.session_id.operating_unit_id.id or order.config_id.operating_unit_id.id or False
            )


class OperatingUnit(models.Model):
    _inherit = "operating.unit"

    pos_config_ids = fields.One2many("pos.config", "operating_unit_id", string="Points of Sale")
