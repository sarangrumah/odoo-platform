# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pdp_masking_policy = fields.Selection(
        [
            ("always_mask", "Always mask (only DPO sees clear)"),
            ("mask_in_export_only", "Mask only in exports"),
            ("unmask_with_reason", "Unmask with reason (audited)"),
        ],
        config_parameter="pdp.masking.policy",
        default="unmask_with_reason",
    )
