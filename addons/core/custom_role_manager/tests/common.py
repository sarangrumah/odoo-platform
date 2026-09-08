# -*- coding: utf-8 -*-
"""Shared fixtures for the role manager tests."""

from __future__ import annotations

from odoo.fields import Command
from odoo.tests.common import TransactionCase


class RoleTestCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Role = cls.env["custom.security.role"]
        cls.Users = cls.env["res.users"]
        cls.Groups = cls.env["res.groups"]

        # Three throw-away groups so the tests never depend on which apps are
        # installed on the database they run against.
        cls.privilege = cls.env["res.groups.privilege"].create({"name": "Role Test"})
        cls.group_a, cls.group_b, cls.group_c = [
            cls.Groups.create({"name": "Role Test / %s" % letter, "privilege_id": cls.privilege.id})
            for letter in ("A", "B", "C")
        ]

    @classmethod
    def _make_user(cls, login, name=None, group_xmlids=()):
        groups = cls.env["res.groups"]
        for xmlid in group_xmlids:
            groups |= cls.env.ref(xmlid)
        return cls.Users.create(
            {
                "login": login,
                "name": name or login,
                "group_ids": [Command.set((groups | cls.env.ref("base.group_user")).ids)],
            }
        )

    @classmethod
    def _make_role(cls, code, groups=(), implies=(), **kwargs):
        vals = {
            "code": code,
            "name": kwargs.pop("name", code.replace("_", " ").title()),
            "group_ids": [Command.set([g.id for g in groups])],
            "implied_role_ids": [Command.set([r.id for r in implies])],
        }
        vals.update(kwargs)
        return cls.Role.create(vals)
