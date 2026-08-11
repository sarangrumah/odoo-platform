# -*- coding: utf-8 -*-
"""The reconciliation engine: what it grants, and — the hard part — what it revokes."""

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from .common import RoleTestCommon


@tagged("post_install", "-at_install")
class TestRoleApply(RoleTestCommon):
    def test_01_apply_grants_groups(self):
        role = self._make_role("t_staff", groups=[self.group_a])
        user = self._make_user("role.staff@test")
        self.assertNotIn(self.group_a, user.group_ids)

        user.write({"role_ids": [Command.link(role.id)]})

        self.assertIn(self.group_a, user.group_ids)
        self.assertIn(self.group_a, user.role_granted_group_ids)

    def test_02_role_closure_follows_implied_roles(self):
        staff = self._make_role("t_staff2", groups=[self.group_a])
        supervisor = self._make_role("t_sup", groups=[self.group_b], implies=[staff])
        manager = self._make_role("t_mgr", groups=[self.group_c], implies=[supervisor])

        user = self._make_user("role.mgr@test")
        user.write({"role_ids": [Command.link(manager.id)]})

        self.assertTrue({self.group_a, self.group_b, self.group_c} <= set(user.group_ids))

    def test_03_swapping_roles_revokes_only_what_roles_granted(self):
        role_1 = self._make_role("t_r1", groups=[self.group_a])
        role_2 = self._make_role("t_r2", groups=[self.group_b])
        user = self._make_user("role.swap@test")

        # A group granted by hand *before* any role: must survive everything.
        user.write({"group_ids": [Command.link(self.group_c.id)]})

        user.write({"role_ids": [Command.link(role_1.id)]})
        self.assertIn(self.group_a, user.group_ids)

        user.write({"role_ids": [Command.set([role_2.id])]})

        self.assertNotIn(self.group_a, user.group_ids, "role 1's group should be revoked")
        self.assertIn(self.group_b, user.group_ids, "role 2's group should be granted")
        self.assertIn(self.group_c, user.group_ids, "hand-granted group must survive")

    def test_04_group_granted_by_another_module_survives(self):
        """A group written directly (as the SSO mapping does) is not in the ledger."""
        role = self._make_role("t_r3", groups=[self.group_a])
        user = self._make_user("role.other@test")
        user.write({"role_ids": [Command.link(role.id)]})

        # Another module grants group_b additively, afterwards.
        user.sudo().write({"group_ids": [Command.link(self.group_b.id)]})

        user.write({"role_ids": [Command.set([])]})

        self.assertNotIn(self.group_a, user.group_ids)
        self.assertIn(self.group_b, user.group_ids)

    def test_05_editing_a_role_resyncs_its_holders(self):
        role = self._make_role("t_r4", groups=[self.group_a])
        user = self._make_user("role.resync@test")
        user.write({"role_ids": [Command.link(role.id)]})

        role.write({"group_ids": [Command.set([self.group_b.id])]})

        self.assertNotIn(self.group_a, user.group_ids)
        self.assertIn(self.group_b, user.group_ids)

    def test_06_editing_an_inherited_role_resyncs_the_parent_holders(self):
        staff = self._make_role("t_r5_staff", groups=[self.group_a])
        manager = self._make_role("t_r5_mgr", groups=[self.group_c], implies=[staff])
        user = self._make_user("role.inherit@test")
        user.write({"role_ids": [Command.link(manager.id)]})

        staff.write({"group_ids": [Command.set([self.group_b.id])]})

        self.assertNotIn(self.group_a, user.group_ids)
        self.assertIn(self.group_b, user.group_ids)
        self.assertIn(self.group_c, user.group_ids)

    def test_07_role_cycle_is_refused(self):
        role_1 = self._make_role("t_c1", groups=[self.group_a])
        role_2 = self._make_role("t_c2", groups=[self.group_b], implies=[role_1])
        with self.assertRaises(ValidationError):
            role_1.write({"implied_role_ids": [Command.set([role_2.id])]})

    def test_08_roles_applied_on_create(self):
        role = self._make_role("t_create", groups=[self.group_a])
        user = self.Users.create(
            {
                "login": "role.create@test",
                "name": "Created With Role",
                "group_ids": [Command.set([self.env.ref("base.group_user").id])],
                "role_ids": [Command.link(role.id)],
            }
        )
        self.assertIn(self.group_a, user.group_ids)

    def test_09_duplicate_code_refused(self):
        self._make_role("t_dup", groups=[self.group_a])
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self._make_role("t_dup", groups=[self.group_b])
