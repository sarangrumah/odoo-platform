# -*- coding: utf-8 -*-
"""Turn the existing Levi's analytic Operating Units into ``operating.unit`` records.

Strictly additive. Nothing is renamed, nothing is archived, nothing is deleted:

* ``stock.warehouse.code`` is the key the retail import (X24/X101) joins on and
  drives the location names, the picking sequences and the store lookup. It is
  never touched — it is *copied* into ``operating.unit.code``.
* ``account.analytic.account.name``, the per-store purchase journal and the
  ``pos.config`` keep the names ``41_normalize_ou.py`` gave them.

What exists today (``custom_levis_localization``):

    res.company.l10n_ho_analytic_id          -> the Head Office unit
    stock.warehouse.l10n_ou_analytic_id      -> one unit per store
    stock.warehouse.l10n_purchase_journal_id -> that store's purchase journal
    pos.config.warehouse_id                  -> that store's point of sale

After this runs, the direction of truth flips: the Operating Unit is the master
and the analytic account is one of its links. The localization keeps working
unchanged — ``account.move.line.l10n_ou_analytic_id`` still drives
``analytic_distribution`` exactly as before.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate_levis_operating_units(env):
    """Idempotent: safe to re-run, creates nothing the second time."""
    OU = env["operating.unit"]
    Warehouse = env["stock.warehouse"].with_context(active_test=False)

    head_offices = {}
    for company in env["res.company"].search([]):
        analytic = company.l10n_ho_analytic_id
        if not analytic:
            continue
        # The head office is a warehouse too (Levi's calls it EBR). Key the unit
        # on that warehouse's code so every unit — head office included — is
        # addressable by the same code the retail import already uses.
        ho_warehouse = Warehouse.search([("l10n_ou_analytic_id", "=", analytic.id)], limit=1)
        head_offices[company.id] = OU._ensure(
            code=(ho_warehouse.code or company.partner_id.ref or "HO"),
            name=analytic.name,
            company=company,
            ou_type="company",
            analytic_account_id=analytic.id,
            warehouse_id=ho_warehouse.id,
            purchase_journal_id=ho_warehouse.l10n_purchase_journal_id.id,
        )
    if not head_offices:
        _logger.warning(
            "No res.company.l10n_ho_analytic_id — is custom_levis_localization seeded? "
            "Stores will be created without a parent."
        )

    created = existing = 0
    for warehouse in Warehouse.search([]):
        analytic = warehouse.l10n_ou_analytic_id
        if not analytic:
            continue
        parent = head_offices.get(warehouse.company_id.id)
        if parent and parent.analytic_account_id == analytic:
            continue  # the head-office warehouse itself, already wired above

        before = OU.with_context(active_test=False).search_count(
            [("code", "=", warehouse.code), ("company_id", "=", warehouse.company_id.id)]
        )
        unit = OU._ensure(
            code=warehouse.code,
            name=analytic.name,
            company=warehouse.company_id,
            ou_type="store",
            parent=parent,
            analytic_account_id=analytic.id,
            warehouse_id=warehouse.id,
            purchase_journal_id=warehouse.l10n_purchase_journal_id.id,
        )
        if before:
            existing += 1
        else:
            created += 1
            # Mirror the store's own state: an archived store gets an archived
            # unit, fully wired, so reactivating it stays a one-liner.
            if not (warehouse.active and analytic.active):
                unit.active = False

    if "pos.config" in env and "operating_unit_id" in env["pos.config"]._fields:
        configs = env["pos.config"].with_context(active_test=False).search([("warehouse_id", "!=", False)])
        for config in configs:
            if config.operating_unit_id:
                continue
            unit = OU.with_context(active_test=False).search([("warehouse_id", "=", config.warehouse_id.id)], limit=1)
            if unit:
                config.operating_unit_id = unit.id

    linked_cash = _link_cash_journals(env, OU)

    _logger.info(
        "Levi's Operating Units: %d head office(s), %d store(s) created, %d already present, "
        "%d cash journal(s) linked.",
        len(head_offices),
        created,
        existing,
        linked_cash,
    )
    return created, existing


def _link_cash_journals(env, OU):
    """Point each store unit at its POS cash journal.

    The store's *purchase* journal comes from the localization and is linked
    above. Its **cash** journal is not: it hangs off the point of sale, as the
    journal of the config's cash payment method. Without this link every POS
    cash entry stays without an Operating Unit — on rnd_levis that was 378
    journal entries and 756 items, which is the difference between a store
    reader seeing their own cash movements and seeing none of them.

    Resolved structurally (config → cash payment method → journal), never by
    matching the journal name against the unit name: the names happen to agree
    today, and a rename would silently stop linking anything.
    """
    if "pos.config" not in env or "journal_id" not in OU._fields:
        return 0
    Config = env["pos.config"].with_context(active_test=False)
    linked = 0
    for unit in OU.with_context(active_test=False).search([("warehouse_id", "!=", False)]):
        if unit.journal_id:
            continue
        configs = Config.search([("warehouse_id", "=", unit.warehouse_id.id)])
        cash_journal = configs.payment_method_ids.filtered(lambda m: m.is_cash_count and m.journal_id)[:1].journal_id
        if cash_journal:
            unit.journal_id = cash_journal.id
            linked += 1
    return linked


def post_init_hook(env):
    migrate_levis_operating_units(env)
