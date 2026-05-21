# -*- coding: utf-8 -*-
"""One withholding line per (vendor bill line × resolved rule).

The line carries the base, tarif and resulting PPh amount. A corresponding
draft ``custom.coretax.bukti.potong`` is materialised so Coretax can
serialise it to XML when the operator runs the export wizard.
"""

from __future__ import annotations

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class WithholdingLine(models.Model):
    _name = "account.move.withholding.line"
    _description = "Account Move Withholding Line"
    _order = "move_id, id"

    move_id = fields.Many2one("account.move", required=True, ondelete="cascade", index=True)
    move_line_id = fields.Many2one(
        "account.move.line", string="Source Move Line", ondelete="set null"
    )
    rule_id = fields.Many2one("tax.withholding.rule", required=True, ondelete="restrict")
    category_id = fields.Many2one(related="rule_id.category_id", store=True, readonly=True)
    pph_kind = fields.Selection(related="rule_id.pph_kind", store=True, readonly=True)

    base_amount = fields.Monetary(required=True, currency_field="currency_id")
    tarif = fields.Float(required=True, digits=(6, 4))
    tax_amount = fields.Monetary(required=True, currency_field="currency_id")

    currency_id = fields.Many2one(related="move_id.currency_id", store=True)
    company_id = fields.Many2one(related="move_id.company_id", store=True)

    bupot_id = fields.Many2one(
        "custom.coretax.bukti.potong",
        string="Bukti Potong",
        ondelete="set null",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._materialise_bupot()
        return recs

    def _materialise_bupot(self):
        Bupot = self.env["custom.coretax.bukti.potong"].sudo()
        for line in self:
            if line.bupot_id:
                continue
            partner = line.move_id.partner_id.commercial_partner_id
            try:
                bupot = Bupot.create({
                    "no_bupot": f"DRAFT-{line.move_id.name or line.move_id.id}-{line.id}",
                    "partner_id": partner.id,
                    # withholding_category.pph_kind uses "pph_23" style; bupot.jenis_pph
                    # expects the bare code ("23", "4_2"). Strip the prefix on write.
                    "jenis_pph": (line.pph_kind or "").removeprefix("pph_"),
                    "tarif": line.tarif,
                    "dpp": line.base_amount,
                    "pph_terpotong": line.tax_amount,
                    "currency_id": line.currency_id.id,
                    "tanggal_bupot": line.move_id.invoice_date or fields.Date.context_today(self),
                    "period_year": (line.move_id.invoice_date or fields.Date.context_today(self)).year,
                    "period_month": (line.move_id.invoice_date or fields.Date.context_today(self)).month,
                    "source": "issued",  # we are the cutter
                    "account_move_id": line.move_id.id,
                    "state": "draft",
                })
                line.bupot_id = bupot.id
            except Exception as e:
                _logger.exception(
                    "Failed to materialise bukti.potong for withholding line %s", line.id
                )
                # Withholding stays — operator can manually create the bupot
                line.move_id.message_post(
                    body=_("Failed to auto-create Bukti Potong: %s") % e
                )
