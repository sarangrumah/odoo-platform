# -*- coding: utf-8 -*-
"""Seed a `petty.cash.type` from each company's pre-0.5.0 configuration.

``post_init_hook`` only fires on install, so an upgrade needs this script.

The module is shared across tenants, and four Levi's databases were already
configured (and hold live requests) before advance types existed. Rather than
force a re-configuration, mirror whatever each company had into a "Petty Cash"
type and back-fill it onto existing requests. The seeded type carries
``limit_enforcement = "off"``, so behaviour after the upgrade is identical to
before it — the new controls are opt-in.

Companies with nothing configured (e.g. ARKA-AIM, which never used the module)
are skipped and left to their own setup script.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Type = env["petty.cash.type"]
    seeded = 0

    for company in env["res.company"].search([]):
        if not company.petty_cash_advance_account_id:
            continue
        if Type.search_count([("company_id", "=", company.id)]):
            continue
        Type.create(
            {
                "name": "Petty Cash",
                "code": "PC",
                "kind": "petty_cash",
                "is_default": True,
                "company_id": company.id,
                "advance_account_id": company.petty_cash_advance_account_id.id,
                "bank_out_journal_id": company.petty_cash_bank_out_journal_id.id,
                "payment_journal_id": company.petty_cash_payment_journal_id.id,
                "expense_journal_id": company.petty_cash_expense_journal_id.id,
                "limit_enforcement": "off",
            }
        )
        seeded += 1

    if seeded:
        _logger.info("custom_petty_cash: seeded %s 'Petty Cash' advance type(s) from company config.", seeded)

    orphans = env["petty.cash.request"].search([("advance_type_id", "=", False)])
    if orphans:
        orphans._pc_assign_default_type()
        _logger.info("custom_petty_cash: back-filled advance type on %s request(s).", len(orphans))
