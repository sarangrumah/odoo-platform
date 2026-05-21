# -*- coding: utf-8 -*-
"""Trigger PPh withholding computation on vendor-bill post."""

from __future__ import annotations

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    x_custom_withholding_line_ids = fields.One2many(
        "account.move.withholding.line", "move_id",
        string="Withholding Lines",
        copy=False,
    )
    x_custom_total_withheld = fields.Monetary(
        string="Total PPh Dipotong",
        compute="_compute_total_withheld",
        store=True,
        currency_field="currency_id",
    )

    @api.depends("x_custom_withholding_line_ids.tax_amount")
    def _compute_total_withheld(self):
        for rec in self:
            rec.x_custom_total_withheld = sum(rec.x_custom_withholding_line_ids.mapped("tax_amount"))

    # ------------------------------------------------------------------

    def _post(self, soft=True):
        # Compute withholding BEFORE super so the journal items can be added
        # as part of the same post operation. We materialise lines + bupot
        # drafts; the journal-item creation is left as a follow-up in P3 when
        # we lock down the per-rule account postings.
        for move in self:
            move._custom_apply_withholding()
        return super()._post(soft=soft)

    def _custom_apply_withholding(self):
        self.ensure_one()
        if self.move_type not in ("in_invoice", "in_refund"):
            return
        # Idempotent — skip if already computed
        if self.x_custom_withholding_line_ids:
            return
        Rule = self.env["tax.withholding.rule"].sudo()
        Line = self.env["account.move.withholding.line"].sudo()
        partner = self.partner_id.commercial_partner_id
        for ml in self.invoice_line_ids:
            # Odoo 19 sets display_type='product' for ordinary invoice product lines
            # (previously False). Skip only true presentational lines.
            if ml.display_type and ml.display_type != "product":
                continue
            rule = Rule._resolve_for_line(ml)
            if not rule:
                continue
            tarif = rule._effective_tarif(partner)
            base = ml.price_subtotal
            tax = round(base * (tarif / 100.0), 2)
            if tax <= 0:
                continue
            Line.create({
                "move_id": self.id,
                "move_line_id": ml.id,
                "rule_id": rule.id,
                "base_amount": base,
                "tarif": tarif,
                "tax_amount": tax,
            })
            try:
                self._pdp_audit_write(
                    "pph_withholding_applied", self.id,
                    {
                        "rule": rule.name,
                        "category_code": rule.category_id.code,
                        "base": base,
                        "tarif": tarif,
                        "tax": tax,
                    },
                )
            except Exception:
                _logger.debug("Withholding audit log write failed for move %s", self.id)
