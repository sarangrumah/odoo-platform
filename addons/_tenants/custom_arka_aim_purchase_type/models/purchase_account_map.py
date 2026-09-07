# -*- coding: utf-8 -*-
"""Trade / Non-Trade account mapping for the ARKA-AIM tenant.

Mirrors ``levis.purchase.account.map``: the two purchase streams post to
different accounts, and because ``account.account.code`` is company-dependent in
Odoo 19 (and the numeric ids differ per database) the wiring lives in a data
table keyed by ``(company, purchase_type)`` rather than in hard xml-ids.

Rows are seeded idempotently by code lookup in the post-init hook and can be
retuned from Accounting > Configuration > Trade/Non-Trade Accounts.
"""

from odoo import api, fields, models


class ArkaPurchaseAccountMap(models.Model):
    _name = "arka.purchase.account.map"
    _description = "ARKA-AIM Trade/Non-Trade Purchase Account Mapping"
    _order = "company_id, purchase_type"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        ondelete="cascade",
    )
    purchase_type = fields.Selection(
        [("trade", "Trade"), ("non_trade", "Non-Trade")],
        string="Purchase Type",
        required=True,
    )
    payable_account_id = fields.Many2one(
        "account.account",
        string="Payable Account",
        domain="[('account_type', '=', 'liability_payable')]",
        check_company=True,
        help="Payable (AP) control account used on the vendor bill for this stream.",
    )
    grir_account_id = fields.Many2one(
        "account.account",
        string="GR/IR Clearing Account",
        check_company=True,
        help="Goods-received/invoice-received clearing account the vendor bill debits "
        "for this stream, so the receipt accrual nets to zero. Only used for "
        "PO-linked product lines of a real-time valued category. Leave empty for "
        "Trade to keep each product category's own stock-variation account.",
    )
    expense_account_id = fields.Many2one(
        "account.account",
        string="Default Expense Account",
        check_company=True,
        help="Fallback expense account for this stream, used only when a bill line "
        "has no account of its own. A product/category account always wins.",
    )

    _company_type_uniq = models.Constraint(
        "unique(company_id, purchase_type)",
        "Only one account mapping per company and purchase type is allowed.",
    )

    @api.depends("company_id", "purchase_type")
    def _compute_display_name(self):
        labels = dict(self._fields["purchase_type"]._description_selection(self.env))
        for rec in self:
            rec.display_name = "%s / %s" % (
                rec.company_id.name or "",
                labels.get(rec.purchase_type, rec.purchase_type or ""),
            )

    @api.model
    def _get_map(self, company, purchase_type):
        """Mapping row for ``company``/``purchase_type``, or an empty recordset."""
        if not company or not purchase_type:
            return self.browse()
        return self.sudo().search(
            [
                ("company_id", "=", company.id),
                ("purchase_type", "=", purchase_type),
            ],
            limit=1,
        )
