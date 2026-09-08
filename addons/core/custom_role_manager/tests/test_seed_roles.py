# -*- coding: utf-8 -*-
"""The shipped catalogue: idempotent, tenant-tolerant, and it never clobbers local edits."""

from odoo.fields import Command
from odoo.tests import tagged

from ..data.seed_roles import SEED_ROLES, sync_seed_roles
from .common import RoleTestCommon


@tagged("post_install", "-at_install")
class TestSeedRoles(RoleTestCommon):
    def test_01_seed_roles_installed(self):
        codes = {spec["code"] for spec in SEED_ROLES}
        found = self.Role.with_context(active_test=False).search([("code", "in", list(codes))])
        self.assertEqual(len(found), len(codes), "post_init_hook should have created every seed role")
        self.assertTrue(all(found.mapped("is_seed")))

    def test_02_sync_is_idempotent(self):
        before = self.Role.with_context(active_test=False).search_count([])
        sync_seed_roles(self.env)
        after = self.Role.with_context(active_test=False).search_count([])
        self.assertEqual(before, after)

    def test_03_missing_group_xmlid_is_skipped_not_fatal(self):
        """A tenant without POS/Coretax must still load the catalogue.

        And once the app *is* installed, the next module update must pick the
        group up — which is why the sync runs from a non-noupdate <function>
        rather than only from a post-init hook.
        """
        role = self.Role.search([("code", "=", "store_cashier")], limit=1)
        self.assertTrue(role, "the role exists even where point_of_sale is absent")
        pos_group = self.env.ref("point_of_sale.group_pos_user", raise_if_not_found=False)
        if pos_group:
            self.assertIn(pos_group, role.group_ids)
        else:
            self.assertFalse(role.group_ids.filtered(lambda g: "POS" in g.name))

    def test_04_customized_seed_role_is_not_overwritten(self):
        role = self.Role.search([("code", "=", "store_stock_keeper")], limit=1)
        role.write({"group_ids": [Command.set([self.group_a.id])]})
        self.assertTrue(role.customized, "an admin edit flags the role as customized")

        sync_seed_roles(self.env)

        self.assertEqual(role.group_ids, self.group_a, "the local composition must survive a resync")

    def test_05_seed_sync_context_does_not_flag_customized(self):
        role = self.Role.search([("code", "=", "hq_auditor")], limit=1)
        self.assertFalse(role.customized)
        sync_seed_roles(self.env)
        self.assertFalse(role.customized)

    def test_06_implied_roles_wired(self):
        manager = self.Role.search([("code", "=", "hq_acc_manager")], limit=1)
        supervisor = self.Role.search([("code", "=", "hq_acc_supervisor")], limit=1)
        self.assertIn(supervisor, manager.implied_role_ids)
        # ... and the closure reaches the staff groups two levels down.
        staff = self.Role.search([("code", "=", "hq_acc_staff_ap")], limit=1)
        self.assertTrue(staff.group_ids <= manager._all_group_ids())
