# -*- coding: utf-8 -*-
"""Keycloak role names resolved through custom.security.role, with the old map intact."""

from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSsoRoleDelegation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.has_roles = "custom.security.role" in cls.env
        cls.privilege = cls.env["res.groups.privilege"].create({"name": "SSO Test"})
        cls.group_x, cls.group_y = [
            cls.env["res.groups"].create(
                {"name": "SSO Test / %s" % letter, "privilege_id": cls.privilege.id}
            )
            for letter in ("X", "Y")
        ]
        cls.user = cls.env["res.users"].create(
            {
                "login": "sso.role@test",
                "name": "SSO user",
                "group_ids": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )

    def _claims(self, *roles):
        return {"realm_access": {"roles": list(roles)}}

    def test_01_role_code_is_matched_and_applied(self):
        if not self.has_roles:
            self.skipTest("custom_role_manager not installed")
        role = self.env["custom.security.role"].create(
            {"code": "sso_test_role", "name": "SSO Test Role",
             "group_ids": [Command.set([self.group_x.id])]}
        )

        self.user._finance_sso_apply_roles(self._claims("sso_test_role"))

        self.assertIn(role, self.user.role_ids)
        self.assertIn(self.group_x, self.user.group_ids, "the role engine applied the groups")

    def test_02_unmatched_names_still_use_the_group_map(self):
        """A tenant migrates one role at a time; the legacy map keeps working."""
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_finance_portal_sso.role_group_map",
            '{"legacy_name": "base.group_partner_manager"}',
        )

        self.user._finance_sso_apply_roles(self._claims("legacy_name"))

        self.assertIn(self.env.ref("base.group_partner_manager"), self.user.group_ids)

    def test_03_additive_by_default(self):
        if not self.has_roles:
            self.skipTest("custom_role_manager not installed")
        role_a = self.env["custom.security.role"].create(
            {"code": "sso_role_a", "name": "SSO Role A",
             "group_ids": [Command.set([self.group_x.id])]}
        )
        role_b = self.env["custom.security.role"].create(
            {"code": "sso_role_b", "name": "SSO Role B",
             "group_ids": [Command.set([self.group_y.id])]}
        )

        self.user._finance_sso_apply_roles(self._claims("sso_role_a"))
        self.user._finance_sso_apply_roles(self._claims("sso_role_b"))

        self.assertIn(role_a, self.user.role_ids, "a sign-in never takes rights away")
        self.assertIn(role_b, self.user.role_ids)

    def test_04_authoritative_mode_mirrors_the_provider(self):
        if not self.has_roles:
            self.skipTest("custom_role_manager not installed")
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_finance_portal_sso.roles_authoritative", "1"
        )
        role_a = self.env["custom.security.role"].create(
            {"code": "sso_auth_a", "name": "SSO Auth A",
             "group_ids": [Command.set([self.group_x.id])]}
        )
        role_b = self.env["custom.security.role"].create(
            {"code": "sso_auth_b", "name": "SSO Auth B",
             "group_ids": [Command.set([self.group_y.id])]}
        )

        self.user._finance_sso_apply_roles(self._claims("sso_auth_a"))
        self.user._finance_sso_apply_roles(self._claims("sso_auth_b"))

        self.assertNotIn(role_a, self.user.role_ids, "the provider owns the list")
        self.assertIn(role_b, self.user.role_ids)
        self.assertNotIn(self.group_x, self.user.group_ids)
        self.assertIn(self.group_y, self.user.group_ids)
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_finance_portal_sso.roles_authoritative", "0"
        )

    def test_05_hand_granted_group_survives_authoritative_mode(self):
        """The engine only ever revokes what it granted itself."""
        if not self.has_roles:
            self.skipTest("custom_role_manager not installed")
        self.user.sudo().write({"group_ids": [Command.link(self.group_x.id)]})
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_finance_portal_sso.roles_authoritative", "1"
        )
        self.env["custom.security.role"].create(
            {"code": "sso_keep", "name": "SSO Keep",
             "group_ids": [Command.set([self.group_y.id])]}
        )

        self.user._finance_sso_apply_roles(self._claims("sso_keep"))

        self.assertIn(self.group_x, self.user.group_ids)
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_finance_portal_sso.roles_authoritative", "0"
        )

    def test_06_no_claims_is_harmless(self):
        before = self.user.group_ids
        self.user._finance_sso_apply_roles({})
        self.assertEqual(self.user.group_ids, before)
