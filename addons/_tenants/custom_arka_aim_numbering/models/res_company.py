# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    x_doc_code = fields.Char(
        string="Document Code",
        help="Short company code used in document numbers, e.g. ARKA or AIM "
        "(SQ/<CODE>/YYYY/MM/NNN). Leave empty to keep standard Odoo numbering "
        "for this company. Set automatically on install for known ARKA/AIM "
        "companies; editable here.",
    )
