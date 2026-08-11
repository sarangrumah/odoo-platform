# -*- coding: utf-8 -*-
"""Shared fixtures for the Operating Unit tests."""

from __future__ import annotations

from odoo.fields import Command
from odoo.tests.common import TransactionCase


class OperatingUnitTestCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.OU = cls.env["operating.unit"]
        cls.Users = cls.env["res.users"]
        cls.company = cls.env.company

        # HO ── Area Jakarta ── Store A / Store B
        #    └─ Store C (directly under HO)
        #
        # Codes are prefixed and the head office is reused when the database
        # already has one: these tests also run on a tenant clone, where real
        # units exist and "HO" is taken.
        cls.ou_ho = cls._head_office()
        cls.ou_area = cls._make_ou("ZZ-AREA", "Area Jakarta", ou_type="area", parent=cls.ou_ho)
        cls.ou_store_a = cls._make_ou("ZZ-A", "Store A", parent=cls.ou_area)
        cls.ou_store_b = cls._make_ou("ZZ-B", "Store B", parent=cls.ou_area)
        cls.ou_store_c = cls._make_ou("ZZ-C", "Store C", parent=cls.ou_ho)

    @classmethod
    def _head_office(cls):
        existing = cls.env["operating.unit"].with_context(active_test=False).search(
            [("ou_type", "=", "company"), ("company_id", "=", cls.env.company.id)], limit=1
        )
        return existing or cls._make_ou("ZZ-HO", "Head Office", ou_type="company")

    @classmethod
    def _make_ou(cls, code, name, ou_type="store", parent=None, **vals):
        return cls.env["operating.unit"].create(
            dict(
                {
                    "code": code,
                    "name": name,
                    "ou_type": ou_type,
                    "parent_id": parent.id if parent else False,
                    "company_id": cls.env.company.id,
                },
                **vals,
            )
        )

    @classmethod
    def _make_user(cls, login, name=None, group_xmlids=()):
        groups = cls.env.ref("base.group_user")
        for xmlid in group_xmlids:
            groups |= cls.env.ref(xmlid)
        return cls.Users.create(
            {"login": login, "name": name or login, "group_ids": [Command.set(groups.ids)]}
        )

    @classmethod
    def _scoped_user(cls, login, units, group_xmlids=()):
        user = cls._make_user(login, group_xmlids=group_xmlids)
        user.operating_unit_ids = [Command.set([u.id for u in units])]
        return user
