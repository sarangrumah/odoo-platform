# -*- coding: utf-8 -*-
"""Module-wide defaults for retail import, stored as ir.config_parameter."""

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    retail_import_queue_channel = fields.Char(
        string="Queue Job Channel",
        config_parameter="retail_import.queue_channel",
        default="root.retail_import",
        help="queue_job channel used for asynchronous retail imports.",
    )
    retail_import_max_log_lines = fields.Integer(
        string="Max Log Lines per Import",
        config_parameter="retail_import.max_log_lines",
        default=500000,
        help="Cap on stored per-row log lines for one import. Counters stay exact "
             "even when lines are truncated.",
    )
    retail_import_alert_on_failure = fields.Boolean(
        string="Alert on Import Failure",
        config_parameter="retail_import.alert_on_failure",
        help="Fire a best-effort alert when an import fails.",
    )
