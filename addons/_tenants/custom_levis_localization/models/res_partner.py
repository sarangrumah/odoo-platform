# -*- coding: utf-8 -*-
"""Related-party flag on the partner master.

Feature #9 routes the vendor-bill AP account per purchase stream (trade vs
non-trade) through ``levis.purchase.account.map``. The EBR chart splits each of
those streams again by counterparty: third parties vs **related parties** —
companies inside the Erajaya group, e.g. PT Sinar Eka Selaras, which must land on
``2103200001`` / ``2103400001`` instead of the third-party control accounts.

That distinction lives on the partner, not on the purchase order, so it is a
flag here and a second account column on the mapping.
"""

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    l10n_related_party = fields.Boolean(
        string="Related Party",
        tracking=True,
        help="This partner belongs to the group (Erajaya). Its vendor bills post "
        "to the related-party AP control account of the purchase stream instead "
        "of the third-party one.",
    )
