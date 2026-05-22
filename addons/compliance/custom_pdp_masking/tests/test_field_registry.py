# -*- coding: utf-8 -*-
"""Tests for PDP field registry + global read masking hook."""

from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "custom_pdp_masking")
class TestFieldRegistry(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Registry = cls.env["custom.pdp.field.registry"].sudo()
        cls.Partner = cls.env["res.partner"]
        cls.bypass_group = cls.env.ref("custom_pdp_masking.group_view_pii")
        cls.partner = cls.Partner.create(
            {
                "name": "Test Person",
                "email": "test.person@example.com",
                "phone": "+62 812 3456 7890",
                "vat": "0123456789012345",
            }
        )

    def _user_without_bypass(self):
        # Use base.group_user, which is implied by group_custom_user but is
        # NOT in the bypass group.
        user = self.env["res.users"].create(
            {
                "name": "No-PII Reader",
                "login": "no_pii_reader@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        return user

    def test_01_registry_entries_exist_from_seed(self):
        seeded = self.Registry.search(
            [("model_name", "=", "res.partner"), ("field_name", "in", ["email", "phone", "vat"])]
        )
        self.assertGreaterEqual(len(seeded), 3)

    def test_02_user_without_bypass_sees_masked_email(self):
        user = self._user_without_bypass()
        # Ensure the email entry exists with email_domain pattern.
        entry = self.Registry.search(
            [("model_name", "=", "res.partner"), ("field_name", "=", "email")],
            limit=1,
        )
        self.assertTrue(entry)
        # Clear any cached registry lookups on the env, then read as user.
        partner = self.partner.with_user(user)
        rows = partner.read(["email"])
        self.assertTrue(rows)
        masked = rows[0]["email"]
        self.assertNotEqual(masked, "test.person@example.com")
        self.assertTrue(masked.startswith("***@"))

    def test_03_user_with_bypass_sees_cleartext(self):
        user = self.env["res.users"].create(
            {
                "name": "PII Viewer",
                "login": "pii_viewer@example.com",
                "groups_id": [
                    (6, 0, [self.env.ref("base.group_user").id, self.bypass_group.id]),
                ],
            }
        )
        partner = self.partner.with_user(user)
        rows = partner.read(["email"])
        self.assertEqual(rows[0]["email"], "test.person@example.com")

    def test_04_field_existence_validation(self):
        from odoo.exceptions import ValidationError

        partner_model = self.env.ref("base.model_res_partner")
        with self.assertRaises(ValidationError):
            self.Registry.create(
                {
                    "model_id": partner_model.id,
                    "field_name": "this_field_does_not_exist",
                    "pii_category": "other",
                    "mask_pattern": "redacted",
                }
            )

    def test_05_discovery_wizard_finds_candidates(self):
        wizard = self.env["custom.pdp.field.discovery.wizard"].create({})
        wizard.action_scan()
        # Should at least find some candidates across installed models.
        self.assertIn("Discovered", wizard.report or "")
