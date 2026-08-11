# -*- coding: utf-8 -*-
"""Fixtures: two units, each with its own warehouse and journal, and users on both."""

from __future__ import annotations

from odoo.fields import Command
from odoo.tests.common import TransactionCase


class OperatingUnitDocsCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.OU = cls.env["operating.unit"]
        cls.Move = cls.env["account.move"]
        cls.company = cls.env.company

        cls.wh_a = cls.env["stock.warehouse"].create(
            {"name": "OU Test WH A", "code": "ZZA", "company_id": cls.company.id}
        )
        cls.wh_b = cls.env["stock.warehouse"].create(
            {"name": "OU Test WH B", "code": "ZZB", "company_id": cls.company.id}
        )
        cls.journal_a = cls.env["account.journal"].create(
            {"name": "Purchase A", "type": "purchase", "code": "ZZPA", "company_id": cls.company.id}
        )
        cls.journal_b = cls.env["account.journal"].create(
            {"name": "Purchase B", "type": "purchase", "code": "ZZPB", "company_id": cls.company.id}
        )

        # Reuse the tenant's head office when there is one: these tests also
        # run against a real clone, where a company-type unit already exists.
        cls.ou_ho = cls.OU.with_context(active_test=False).search(
            [("ou_type", "=", "company"), ("company_id", "=", cls.company.id)], limit=1
        ) or cls.OU.create(
            {"code": "ZZ-HO", "name": "Head Office", "ou_type": "company",
             "company_id": cls.company.id}
        )
        cls.ou_a = cls.OU.create(
            {
                "code": "ZZ-A",
                "name": "Store A",
                "parent_id": cls.ou_ho.id,
                "company_id": cls.company.id,
                "warehouse_id": cls.wh_a.id,
                "purchase_journal_id": cls.journal_a.id,
            }
        )
        cls.ou_b = cls.OU.create(
            {
                "code": "ZZ-B",
                "name": "Store B",
                "parent_id": cls.ou_ho.id,
                "company_id": cls.company.id,
                "warehouse_id": cls.wh_b.id,
                "purchase_journal_id": cls.journal_b.id,
            }
        )

        cls.user_store_a = cls._make_user("ou.docs.a@test", [cls.ou_a])
        cls.user_hq = cls._make_user("ou.docs.hq@test", [])

    @classmethod
    def _make_user(cls, login, units):
        groups = (
            cls.env.ref("base.group_user")
            | cls.env.ref("account.group_account_user")
            | cls.env.ref("custom_operating_unit.group_operating_unit_user")
        )
        user = cls.env["res.users"].create(
            {"login": login, "name": login, "group_ids": [Command.set(groups.ids)]}
        )
        if units:
            user.operating_unit_ids = [Command.set([u.id for u in units])]
        return user

    @classmethod
    def _make_move(cls, unit, journal=None):
        return cls.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": (journal or cls.journal_a).id,
                "operating_unit_id": unit.id if unit else False,
            }
        )
