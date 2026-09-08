# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    x_custom_show_date_enabled = fields.Boolean(
        string="Enable Show Date (ARKA)",
        default=False,
        help="When enabled, quotations/sales orders for this company capture a "
        "required Show Date, and customer-invoice payment-term due dates are "
        "anchored to the Show Date instead of the invoice date. Intended for "
        "PT ARKA only; leave off for every other company.",
    )
    x_custom_event_tracking_enabled = fields.Boolean(
        string="Enable Event Tracking (analytic per event)",
        default=False,
        help="When enabled, sales orders, purchase orders and bills of this "
        "company are tagged with an analytic account named after their event "
        '("<event> - <location> - <dd.mm.yy>"), so Profit & Loss can be read '
        "per event. Unlike Show Date this makes nothing required and changes no "
        "due date, so it is safe to enable on BOTH sister companies — which is "
        "what makes a cross-company P&L per event possible.",
    )
