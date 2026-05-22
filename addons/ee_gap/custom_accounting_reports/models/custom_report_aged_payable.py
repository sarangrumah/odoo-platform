# -*- coding: utf-8 -*-
"""Aged Payable: open AP per vendor bucketed by overdue days."""

from odoo import models


class CustomReportAgedPayable(models.AbstractModel):
    _name = "custom.report.aged.payable"
    _inherit = "custom.report.aged.receivable"
    _description = "Custom Aged Payable"

    _report_code = "aged_payable"
    _report_title = "Aged Payable"

    def _account_type(self):
        return "liability_payable"
