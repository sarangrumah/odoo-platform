# -*- coding: utf-8 -*-
"""Ship the tax identity to the POS client.

The cashier needs to see, in the customer list, whether the buyer already
carries an NPWP — otherwise the only way to find out is to invoice and hit the
guard in ``pos.order``. The field is loaded read-only for display; editing
still happens in the standard partner form, which ``custom_tax_id`` already
extends.
"""

from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        for name in ("x_custom_npwp", "x_custom_nik"):
            if name in self._fields and name not in fields:
                fields.append(name)
        return fields
