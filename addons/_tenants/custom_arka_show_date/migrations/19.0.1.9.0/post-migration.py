# -*- coding: utf-8 -*-
"""Give the event analytic accounts created before 1.9.0 their show date.

``account.analytic.account.x_custom_event_show_date`` is new in 1.9.0 and is how
the overhead allocation picks the events of a period. Accounts created by 1.7.0
and 1.8.0 have it empty, and parsing the date back out of the "<event> -
<location> - <dd.mm.yy>" name would be exactly the fragility the field exists to
avoid. The documents that created those accounts still carry the date, so read
it from them.

Idempotent: only fills what is empty.
"""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    plan = env.ref("custom_arka_show_date.analytic_plan_arka_event", raise_if_not_found=False)
    if not plan:
        return

    missing = (
        env["account.analytic.account"]
        .with_context(active_test=False)
        .search([("plan_id", "=", plan.id), ("x_custom_event_show_date", "=", False)])
    )
    if not missing:
        return

    # Resolving an event from a document is self-healing since 1.9.0: it stamps
    # the show date onto the account it finds. Walk every document that carries
    # event data and let it heal its own account.
    for model in ("sale.order", "purchase.order", "account.move"):
        records = env[model].search([("x_custom_event_name", "!=", False)])
        for record in records:
            account = record._custom_event_analytic_account(create=False)
            if account and not account.x_custom_event_show_date:
                _name, _location, show_date = record._custom_event_values()
                if show_date:
                    account.x_custom_event_show_date = show_date

    still_empty = missing.filtered(lambda account: not account.x_custom_event_show_date)
    if still_empty:
        # Not fatal: an event nobody dated simply cannot be picked by period,
        # and the allocation form will not offer it. Say so rather than guess.
        env["ir.logging"].sudo().create(
            {
                "name": "custom_arka_show_date",
                "type": "server",
                "level": "WARNING",
                "dbname": cr.dbname,
                "message": "Event analytic accounts left without a show date: %s"
                % ", ".join(still_empty.mapped("display_name")),
                "path": "migrations/19.0.1.9.0/post-migration.py",
                "func": "migrate",
                "line": "0",
            }
        )
