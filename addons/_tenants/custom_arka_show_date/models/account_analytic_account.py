# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = "account.analytic.account"

    x_custom_event_key = fields.Char(
        string="Event Key",
        index=True,
        copy=False,
        help="Normalised '<event> - <location> - <dd.mm.yy>' label used to match "
        "a sales order, purchase order or bill to its event analytic account. "
        "Case and spacing are folded away so the same show typed three ways "
        "still resolves to one account. Set automatically; leave empty on "
        "analytic accounts that are not events.",
    )

    x_custom_event_show_date = fields.Date(
        string="Show Date",
        index="btree_not_null",
        copy=False,
        help="The show this event account stands for. Kept as a real date, not "
        "parsed back out of the name, so a period can be selected reliably — "
        "the overhead allocation picks the events of a period by this field.",
    )

    # One event, one analytic account — the whole cross-company P&L rests on
    # that. NULL keys are exempt (Postgres), so ordinary analytic accounts and
    # the other plans are untouched.
    _custom_event_key_uniq = models.Constraint(
        "unique (x_custom_event_key)",
        "An analytic account already exists for this event.",
    )
