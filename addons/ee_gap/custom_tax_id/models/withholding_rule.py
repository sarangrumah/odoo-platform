# -*- coding: utf-8 -*-
"""Withholding rule: (category × condition) → tarif + hutang account.

A rule resolves at vendor-bill-post time. Resolution priority:
  1. Product-category override (explicit), highest priority.
  2. Partner-category override.
  3. Generic rule with empty filters.
"""

from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WithholdingRule(models.Model):
    _name = "tax.withholding.rule"
    _description = "PPh Withholding Rule"
    _order = "priority desc, sequence, id"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    priority = fields.Integer(
        default=10,
        help="Higher priority wins. Use product/partner-specific overrides at >50.",
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, ondelete="cascade"
    )

    category_id = fields.Many2one("tax.withholding.category", required=True, ondelete="restrict")
    pph_kind = fields.Selection(related="category_id.pph_kind", store=True, readonly=True)

    tarif = fields.Float(
        string="Tarif (%)", digits=(6, 4), required=True,
        help="Withholding rate as a percent. e.g. 2.0 = 2%.",
    )
    tarif_no_npwp = fields.Float(
        string="Tarif (Tanpa NPWP) (%)", digits=(6, 4),
        help="Bumped rate applied when vendor has no valid NPWP. "
             "Typical PPh 23: 2% → 4%. Leave 0 to fall back to the base tarif.",
    )

    account_id = fields.Many2one(
        "account.account",
        string="Account Hutang Pajak",
        domain="[('company_ids','in',company_id),('account_type','=','liability_current')]",
        help="Liability account credited when withholding is recognised. "
             "Required before the rule can be activated.",
    )

    # ---- Filters that narrow the resolution ----
    product_category_ids = fields.Many2many(
        "product.category",
        "tax_wh_rule_prod_cat_rel",
        "rule_id", "category_id",
        string="Product Categories",
        help="Apply only when the bill line's product belongs to one of these categories. "
             "Empty = no product-category filter.",
    )
    partner_category_ids = fields.Many2many(
        "res.partner.category",
        "tax_wh_rule_part_cat_rel",
        "rule_id", "tag_id",
        string="Partner Tags",
        help="Apply only when the vendor has one of these tags. Empty = no filter.",
    )
    foreign_only = fields.Boolean(
        string="Foreign Counterparty Only",
        help="Apply only when vendor's country differs from company country. "
             "Used to switch from PPh 23 → PPh 26.",
    )

    notes = fields.Text()

    @api.constrains("tarif", "tarif_no_npwp")
    def _check_tarif(self):
        for rec in self:
            if rec.tarif < 0 or rec.tarif > 100:
                raise ValidationError(_("Tarif must be between 0 and 100 percent."))
            if rec.tarif_no_npwp and (rec.tarif_no_npwp < 0 or rec.tarif_no_npwp > 100):
                raise ValidationError(_("Tarif without NPWP must be between 0 and 100 percent."))

    @api.constrains("active", "account_id")
    def _check_account_when_active(self):
        for rec in self:
            if rec.active and not rec.account_id:
                raise ValidationError(_(
                    "Rule '%s' cannot be activated without an Account Hutang Pajak. "
                    "Set the liability account before activating.", rec.name,
                ))

    # ------------------------------------------------------------------

    @api.model
    def _resolve_for_line(self, move_line):
        """Return the best-matching active rule for ``move_line``, or empty recordset.

        ``move_line`` is an ``account.move.line`` on a vendor bill.
        """
        if not move_line or move_line.move_id.move_type not in ("in_invoice", "in_refund"):
            return self.browse()

        partner = move_line.move_id.partner_id.commercial_partner_id
        company = move_line.move_id.company_id
        is_foreign = bool(
            partner.country_id and company.country_id and partner.country_id != company.country_id
        )
        product_categ = move_line.product_id.categ_id
        partner_tags = partner.category_id

        candidates = self.sudo().search([
            ("active", "=", True),
            ("company_id", "in", (False, company.id)),
        ], order="priority desc, sequence asc")

        for rule in candidates:
            if rule.foreign_only and not is_foreign:
                continue
            if rule.product_category_ids:
                if not product_categ or product_categ not in rule.product_category_ids:
                    continue
            if rule.partner_category_ids:
                if not (rule.partner_category_ids & partner_tags):
                    continue
            return rule
        return self.browse()

    def _effective_tarif(self, vendor):
        """Return the rate that actually applies given vendor's NPWP status."""
        self.ensure_one()
        if self.tarif_no_npwp and not vendor.x_custom_has_valid_npwp:
            return self.tarif_no_npwp
        return self.tarif
