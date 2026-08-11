# -*- coding: utf-8 -*-
"""Operating Unit on accounting documents.

The move is the master: its unit cascades to its lines, its payment and its
statement line. A line may still override it (a head-office bill split across
stores), which is why the computes never overwrite a value that is already set.
"""

from odoo import api, fields, models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "operating.unit.mixin"]

    operating_unit_id = fields.Many2one(
        compute="_compute_operating_unit_id",
        store=True,
        readonly=False,
    )

    @api.depends("journal_id")
    def _compute_operating_unit_id(self):
        journal_index = self.env["operating.unit"]._journal_index()
        default_unit = self.env.user.default_operating_unit_id
        for move in self:
            if move.operating_unit_id:
                continue
            unit_id = journal_index.get(move.journal_id.id)
            move.operating_unit_id = unit_id or default_unit.id or False


class AccountMoveLine(models.Model):
    _name = "account.move.line"
    _inherit = ["account.move.line", "operating.unit.mixin"]

    operating_unit_id = fields.Many2one(
        compute="_compute_operating_unit_id",
        store=True,
        readonly=False,
    )

    @api.depends("move_id.operating_unit_id", "analytic_distribution")
    def _compute_operating_unit_id(self):
        analytic_index = self.env["operating.unit"]._analytic_index()
        for line in self:
            if line.operating_unit_id:
                continue
            unit_id = line.move_id.operating_unit_id.id
            if not unit_id and line.analytic_distribution:
                unit_id = self._ou_from_distribution(line.analytic_distribution, analytic_index)
            line.operating_unit_id = unit_id or False

    @api.model
    def _ou_from_distribution(self, distribution, analytic_index):
        """First unit referenced by an ``analytic_distribution`` JSON.

        Odoo joins the analytic ids of several plans into one comma-separated
        key ("12,45"), which is also why this dimension cannot be filtered
        through the JSONB in a record-rule domain at any sane cost.
        """
        for key in distribution or {}:
            for part in str(key).split(","):
                part = part.strip()
                if part.isdigit():
                    unit_id = analytic_index.get(int(part))
                    if unit_id:
                        return unit_id
        return False


class AccountPayment(models.Model):
    _name = "account.payment"
    _inherit = ["account.payment", "operating.unit.mixin"]

    operating_unit_id = fields.Many2one(related="move_id.operating_unit_id", store=True, readonly=False, index=True)


class AccountBankStatementLine(models.Model):
    _name = "account.bank.statement.line"
    _inherit = ["account.bank.statement.line", "operating.unit.mixin"]

    operating_unit_id = fields.Many2one(related="move_id.operating_unit_id", store=True, readonly=False, index=True)
