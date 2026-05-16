# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Field is prefixed with `x_custom_vertical_example_` per the vertical
    # naming rule. When forking this template rename the prefix to
    # match the new vertical slug.
    x_custom_vertical_example_tag = fields.Char(
        string="Vertical Example Tag",
        default="example",
        help="Free-form tag used by the Custom Vertical (Example) module. "
             "Replace with vertical-specific fields when forking.",
    )
