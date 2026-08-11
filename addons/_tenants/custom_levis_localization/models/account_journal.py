# -*- coding: utf-8 -*-
"""Which narrative grammar a bank feed speaks.

The clearing has to read gross and MDR out of ``payment_ref``, and every bank
writes that line differently: BCA uses ``TGH:``/``DDR:``/``ADM:`` with English
decimals, BRI uses ``AMT:``/``MDR:`` with Indonesian ones. The grammar belongs to
the feed, not to the store, so the parser strategy is selected here rather than
guessed from the journal code — codes (``IBCA``, ``OBCA``, ``IBRI``) are a
per-database naming convention and would not survive the next tenant.
"""

from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    levis_clearing_format = fields.Selection(
        [
            ("bca", "BCA"),
            ("bri", "BRI"),
            ("bni", "BNI"),
            ("mandiri", "Mandiri"),
            ("none", "Not Parsed"),
        ],
        string="Clearing Narrative Format",
        help="Grammar used to read the settlement gross and MDR out of this "
        "journal's statement narratives. Leave empty or set to Not Parsed and the "
        "clearing will list the lines as unparsed instead of guessing.",
    )
