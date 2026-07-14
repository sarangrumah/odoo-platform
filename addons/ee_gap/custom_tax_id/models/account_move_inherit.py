# -*- coding: utf-8 -*-
"""Trigger PPh withholding computation on vendor-bill post."""

from __future__ import annotations

import logging

from odoo import Command, _, api, fields, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    x_custom_withholding_line_ids = fields.One2many(
        "account.move.withholding.line",
        "move_id",
        string="Withholding Lines",
        copy=False,
    )
    x_custom_total_withheld = fields.Monetary(
        string="Total PPh Dipotong",
        compute="_compute_total_withheld",
        store=True,
        currency_field="currency_id",
    )
    x_custom_withholding_move_id = fields.Many2one(
        "account.move",
        string="Jurnal Pemotongan PPh",
        copy=False,
        readonly=True,
        help="Journal entry that books the PPh withholding to the GL "
        "(Dr Utang Usaha / Cr Hutang PPh). Created on post when "
        "``custom_tax_id.withholding_gl_posting`` is enabled.",
    )

    @api.depends("x_custom_withholding_line_ids.tax_amount")
    def _compute_total_withheld(self):
        for rec in self:
            rec.x_custom_total_withheld = sum(rec.x_custom_withholding_line_ids.mapped("tax_amount"))

    # ------------------------------------------------------------------

    def _post(self, soft=True):
        # Materialise withholding lines + bupot drafts BEFORE super so they are
        # available on the freshly-posted move.
        for move in self:
            move._custom_apply_withholding()
        posted = super()._post(soft=soft)
        # Book the withholding to the GL AFTER super so the payable line exists.
        for move in posted:
            move._custom_post_withholding_entry()
        return posted

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
            Line.create(
                {
                    "move_id": self.id,
                    "move_line_id": ml.id,
                    "rule_id": rule.id,
                    "base_amount": base,
                    "tarif": tarif,
                    "tax_amount": tax,
                }
            )
            try:
                self._pdp_audit_write(
                    "pph_withholding_applied",
                    self.id,
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

    # ------------------------------------------------------------------
    # GL posting for the withholding (the "P3 follow-up" — now implemented)
    # ------------------------------------------------------------------
    def _custom_post_withholding_entry(self):
        """Book the PPh withholding to the GL as a separate posted entry.

        We are the *pemotong*: we withhold PPh from what we owe the vendor and
        now owe it to DJP. Accounting (vendor bill, ``in_invoice``):

            Dr Utang Usaha (AP)   total PPh   -> reduce the vendor payable
            Cr Hutang PPh (rule)  total PPh   -> liability to the state

        For ``in_refund`` the legs are reversed. The entry is NOT auto-reconciled
        against the bill: the AP clerk reconciles the bill credit against the
        withholding debit + the (net) vendor payment together, keeping the
        normal payment flow intact.

        Gated by ``ir.config_parameter`` ``custom_tax_id.withholding_gl_posting``
        (default enabled) and idempotent via ``x_custom_withholding_move_id``.
        """
        self.ensure_one()
        if self.move_type not in ("in_invoice", "in_refund"):
            return
        if self.x_custom_withholding_move_id:
            return
        enabled = self.env["ir.config_parameter"].sudo().get_param("custom_tax_id.withholding_gl_posting", "1")
        if str(enabled).lower() not in ("1", "true"):
            return
        if not self.x_custom_withholding_line_ids:
            return

        ap_line = self.line_ids.filtered(lambda l: l.account_id.account_type == "liability_payable")[:1]
        if not ap_line:
            return

        per_account = {}
        for wl in self.x_custom_withholding_line_ids:
            acc = wl.rule_id.account_id
            if not acc:
                continue
            per_account[acc.id] = per_account.get(acc.id, 0.0) + (wl.tax_amount or 0.0)
        total = sum(per_account.values())
        if not total:
            return

        journal = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.company_id.id)],
            limit=1,
        )
        if not journal:
            _logger.warning(
                "custom_tax_id: no general journal for company %s; skipping withholding GL entry for %s",
                self.company_id.id,
                self.name,
            )
            return

        ap_is_debit = self.move_type == "in_invoice"
        je_lines = [
            Command.create(
                {
                    "account_id": ap_line.account_id.id,
                    "partner_id": self.partner_id.id,
                    "name": _("Pemotongan PPh — %s") % (self.name or ""),
                    "debit": total if ap_is_debit else 0.0,
                    "credit": 0.0 if ap_is_debit else total,
                }
            )
        ]
        for acc_id, amount in per_account.items():
            je_lines.append(
                Command.create(
                    {
                        "account_id": acc_id,
                        "partner_id": self.partner_id.id,
                        "name": _("Hutang PPh — %s") % (self.name or ""),
                        "debit": 0.0 if ap_is_debit else amount,
                        "credit": amount if ap_is_debit else 0.0,
                    }
                )
            )
        je = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "date": self.invoice_date or self.date or fields.Date.context_today(self),
                "company_id": self.company_id.id,
                "ref": _("Pemotongan PPh atas %s") % (self.name or ""),
                "line_ids": je_lines,
            }
        )
        je.action_post()
        self.x_custom_withholding_move_id = je.id
