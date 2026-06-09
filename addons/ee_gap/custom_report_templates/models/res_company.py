# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    report_bank_details = fields.Text(
        string="Report Bank / Tax Details",
        help="Bank account, NPWP and payment details printed in the "
        "OTHER COMMENTS box of customer invoices. Use line breaks to "
        "separate lines. Per-tenant — each company sets its own.",
    )
    report_footer_note = fields.Char(
        string="Report Footer Note",
        default="Thank You For Your Business",
        help="Short note centred at the bottom of every branded document.",
    )
