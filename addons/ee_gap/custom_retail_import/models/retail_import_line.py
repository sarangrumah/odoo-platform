# -*- coding: utf-8 -*-
from odoo import fields, models


class RetailImportLine(models.Model):
    _name = "retail.import.line"
    _description = "Retail Import Source Row"
    _order = "log_id, row_number"

    log_id = fields.Many2one("retail.import.log", required=True, ondelete="cascade", index=True)
    row_number = fields.Integer(index=True)
    aggregate_key = fields.Char(index=True, help="Grouping key used during aggregation (e.g. product_code, store|date|reg|transnum).")
    raw_data_json = fields.Text(help="Full parsed row dict as JSON. May be purged after a retention period while keeping linkage metadata.")
    state = fields.Selection(
        [("ok", "OK"), ("skipped", "Skipped"), ("error", "Error")],
        default="ok",
        index=True,
    )
    error_message = fields.Text()
    target_model = fields.Char(help="Odoo model name of the record produced from this row.")
    target_res_id = fields.Integer(help="ID of the Odoo record produced from this row (or the aggregate it contributed to).")
