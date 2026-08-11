# -*- coding: utf-8 -*-
"""Who may see what — including the "installing this restricts nobody" promise."""

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged

from .common import OperatingUnitTestCommon


@tagged("post_install", "-at_install")
class TestUserScope(OperatingUnitTestCommon):
    def test_01_unassigned_user_is_unrestricted(self):
        user = self._make_user("ou.none@test")
        self.assertFalse(user.ou_is_scoped)
        self.assertIn(self.ou_store_a, user.ou_allowed_ids)
        self.assertIn(self.ou_ho, user.ou_allowed_ids)

    def test_02_store_user_sees_only_its_own_unit(self):
        user = self._scoped_user("ou.store@test", [self.ou_store_a])
        self.assertTrue(user.ou_is_scoped)
        self.assertEqual(user.ou_allowed_ids, self.ou_store_a)

    def test_03_area_user_gets_the_whole_subtree(self):
        user = self._scoped_user("ou.area@test", [self.ou_area])
        allowed = user.ou_allowed_ids
        self.assertIn(self.ou_area, allowed)
        self.assertIn(self.ou_store_a, allowed)
        self.assertIn(self.ou_store_b, allowed)
        self.assertNotIn(self.ou_store_c, allowed, "another branch of the tree stays out")
        self.assertNotIn(self.ou_ho, allowed, "an area manager does not get Head Office")

    def test_04_all_units_group_overrides_assignment(self):
        user = self._scoped_user(
            "ou.hq@test", [self.ou_store_a], ["custom_operating_unit.group_operating_unit_all"]
        )
        self.assertFalse(user.ou_is_scoped)
        self.assertIn(self.ou_store_c, user.ou_allowed_ids)

    def test_05_all_access_helper_writes_the_group(self):
        user = self._scoped_user("ou.helper@test", [self.ou_store_a])
        self.assertFalse(user.ou_all_access)
        user.ou_all_access = True
        self.assertIn(
            self.env.ref("custom_operating_unit.group_operating_unit_all"), user.all_group_ids
        )
        self.assertFalse(user.ou_is_scoped)
        user.ou_all_access = False
        self.assertTrue(user.ou_is_scoped)

    def test_06_reparenting_widens_the_subtree(self):
        user = self._scoped_user("ou.reparent@test", [self.ou_area])
        self.assertNotIn(self.ou_store_c, user.ou_allowed_ids)
        self.ou_store_c.write({"parent_id": self.ou_area.id})
        self.assertIn(self.ou_store_c, user.ou_allowed_ids)

    def test_07_record_rule_filters_the_unit_list_itself(self):
        user = self._scoped_user(
            "ou.rule@test", [self.ou_store_a], ["custom_operating_unit.group_operating_unit_user"]
        )
        visible = self.OU.with_user(user).search([])
        self.assertEqual(visible, self.ou_store_a)

    # The write guard itself needs a concrete model carrying the mixin, so it is
    # tested in custom_operating_unit_docs against account.move.

    def test_09_default_unit_must_be_one_of_the_assigned(self):
        user = self._scoped_user("ou.default@test", [self.ou_store_a])
        user.default_operating_unit_id = self.ou_store_a.id
        self.assertEqual(user.default_operating_unit_id, self.ou_store_a)

    def test_10_superuser_is_never_scoped(self):
        root = self.env.ref("base.user_root")
        root.operating_unit_ids = [Command.set([self.ou_store_a.id])]
        self.assertFalse(root.ou_is_scoped, "the superuser must never be locked out")

    def test_11_include_untagged_parameter_is_exposed(self):
        user = self._scoped_user("ou.untagged@test", [self.ou_store_a])
        self.assertTrue(user.ou_include_untagged, "default posture keeps legacy documents visible")
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_operating_unit.include_untagged", "0"
        )
        user.invalidate_recordset(["ou_include_untagged"])
        self.assertFalse(user.ou_include_untagged)

    def test_12_scoped_user_cannot_create_a_unit(self):
        user = self._scoped_user(
            "ou.nocreate@test", [self.ou_store_a], ["custom_operating_unit.group_operating_unit_user"]
        )
        with self.assertRaises(AccessError):
            self.OU.with_user(user).create(
                {"code": "ST-X", "name": "Sneaky", "company_id": self.company.id}
            )
