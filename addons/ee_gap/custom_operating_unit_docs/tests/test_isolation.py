# -*- coding: utf-8 -*-
"""Isolation: what a scoped user reads, and what the server refuses to let them write."""

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import OperatingUnitDocsCommon


@tagged("post_install", "-at_install")
class TestOperatingUnitIsolation(OperatingUnitDocsCommon):
    def test_01_store_user_sees_only_own_unit(self):
        mine = self._make_move(self.ou_a)
        theirs = self._make_move(self.ou_b, journal=self.journal_b)

        visible = self.Move.with_user(self.user_store_a).search([("id", "in", (mine | theirs).ids)])

        self.assertEqual(visible, mine)

    def test_02_untagged_documents_stay_visible_by_default(self):
        """Day-one posture: history has no unit yet, and must not appear to vanish."""
        legacy = self._make_move(None)
        legacy.operating_unit_id = False
        visible = self.Move.with_user(self.user_store_a).search([("id", "=", legacy.id)])
        self.assertEqual(visible, legacy)

    def test_03_untagged_can_be_locked_down_per_tenant(self):
        legacy = self._make_move(None)
        legacy.operating_unit_id = False
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_operating_unit.include_untagged", "0"
        )
        self.user_store_a.invalidate_recordset(["ou_include_untagged"])

        visible = self.Move.with_user(self.user_store_a).search([("id", "=", legacy.id)])

        self.assertFalse(visible)
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_operating_unit.include_untagged", "1"
        )

    def test_04_unscoped_user_sees_everything(self):
        mine = self._make_move(self.ou_a)
        theirs = self._make_move(self.ou_b, journal=self.journal_b)
        visible = self.Move.with_user(self.user_hq).search([("id", "in", (mine | theirs).ids)])
        self.assertEqual(visible, mine | theirs)

    def test_05_write_guard_refuses_a_foreign_unit(self):
        """A record rule alone would not stop this — the constraint does."""
        with self.assertRaises(AccessError):
            self.Move.with_user(self.user_store_a).create(
                {
                    "move_type": "entry",
                    "journal_id": self.journal_b.id,
                    "operating_unit_id": self.ou_b.id,
                }
            )

    def test_06_write_guard_refuses_moving_a_document_afterwards(self):
        """A create-time check alone would miss this."""
        move = self.Move.with_user(self.user_store_a).create(
            {"move_type": "entry", "journal_id": self.journal_a.id}
        )
        self.assertEqual(move.operating_unit_id, self.ou_a)
        with self.assertRaises(AccessError):
            move.write({"operating_unit_id": self.ou_b.id})

    def test_07_sudo_paths_are_unaffected(self):
        """Crons, the retail import and queue_job all run elevated."""
        move = self.Move.with_user(self.user_store_a).sudo().create(
            {
                "move_type": "entry",
                "journal_id": self.journal_b.id,
                "operating_unit_id": self.ou_b.id,
            }
        )
        self.assertEqual(move.operating_unit_id, self.ou_b)

    def test_08_area_user_sees_both_stores(self):
        area = self.OU.create(
            {
                "code": "ZZ-AREA",
                "name": "Area",
                "ou_type": "area",
                "parent_id": self.ou_ho.id,
                "company_id": self.company.id,
            }
        )
        (self.ou_a | self.ou_b).write({"parent_id": area.id})
        area_user = self._make_user("ou.docs.area@test", [area])

        a_move = self._make_move(self.ou_a)
        b_move = self._make_move(self.ou_b, journal=self.journal_b)
        visible = self.Move.with_user(area_user).search([("id", "in", (a_move | b_move).ids)])

        self.assertEqual(visible, a_move | b_move)
