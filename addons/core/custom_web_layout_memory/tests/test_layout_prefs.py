# -*- coding: utf-8 -*-
import json

from odoo.tests import TransactionCase, tagged

from odoo.addons.custom_web_layout_memory.models.res_users_settings import (
    MAX_ENTRIES_PER_SECTION,
    MAX_PREFS_BYTES,
)


@tagged("post_install", "-at_install")
class TestLayoutPrefs(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {
                "name": "Layout Tester",
                "login": "layout.tester@example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.settings = cls.env["res.users.settings"].with_user(cls.user)

    def test_read_before_any_write_creates_nothing(self):
        """Opening a list view must not write to the database.

        `res.users.create` already gives every internal user a settings row, so
        the row is removed first to reproduce the case that matters: a user
        whose settings have never been materialised.
        """
        self.user.res_users_settings_ids.sudo().unlink()
        prefs = self.settings.get_layout_prefs()
        self.assertEqual(prefs, {"columnWidths": {}, "chatterCollapsed": {}})
        self.assertFalse(self.user.res_users_settings_ids, "a read must stay a read")

    def test_round_trip_per_user(self):
        self.settings.set_layout_prefs({"columnWidths": {"account.move|12|abc": {"name": 180, "ref": 90.6}}})
        prefs = self.settings.get_layout_prefs()
        # Widths are rounded server-side: they come from a pixel measurement.
        self.assertEqual(prefs["columnWidths"]["account.move|12|abc"], {"name": 180, "ref": 91})
        # Another user starts clean.
        other = self.env["res.users"].create(
            {
                "name": "Other",
                "login": "other.layout@example.com",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.assertEqual(self.env["res.users.settings"].with_user(other).get_layout_prefs()["columnWidths"], {})

    def test_merge_and_delete(self):
        self.settings.set_layout_prefs({"columnWidths": {"a": {"x": 100}, "b": {"y": 100}}})
        self.settings.set_layout_prefs({"columnWidths": {"a": None}})
        prefs = self.settings.get_layout_prefs()
        self.assertNotIn("a", prefs["columnWidths"], "a reset view must be forgotten")
        self.assertIn("b", prefs["columnWidths"], "other views must survive a reset")

    def test_chatter_flag_is_boolean(self):
        self.settings.set_layout_prefs({"chatterCollapsed": {"account.move": "yes"}})
        self.assertIs(self.settings.get_layout_prefs()["chatterCollapsed"]["account.move"], True)

    def test_garbage_is_dropped_not_raised(self):
        """An older or buggier client must never break the settings write."""
        self.settings.set_layout_prefs(
            {
                "unknownSection": {"a": 1},
                "columnWidths": {
                    "view": {
                        "ok": 120,
                        "too_wide": 99999,
                        "too_narrow": 1,
                        "not_a_number": "180px",
                        "boolish": True,
                    }
                },
            }
        )
        prefs = self.settings.get_layout_prefs()
        self.assertNotIn("unknownSection", prefs)
        self.assertEqual(prefs["columnWidths"]["view"], {"ok": 120})

    def test_unparseable_blob_does_not_poison_reads(self):
        record = self.env["res.users.settings"]._find_or_create_for_user(self.user)
        record.sudo().layout_prefs = "not json at all"
        self.assertEqual(self.settings.get_layout_prefs(), {"columnWidths": {}, "chatterCollapsed": {}})

    def test_pruning_keeps_the_blob_bounded(self):
        self.settings.set_layout_prefs(
            {"columnWidths": {f"view-{i}": {"name": 100 + i} for i in range(MAX_ENTRIES_PER_SECTION + 25)}}
        )
        record = self.env["res.users.settings"]._find_or_create_for_user(self.user)
        stored = json.loads(record.sudo().layout_prefs)
        self.assertEqual(len(stored["columnWidths"]), MAX_ENTRIES_PER_SECTION)
        self.assertNotIn("view-0", stored["columnWidths"], "coldest entries go first")
        self.assertIn("view-324", stored["columnWidths"], "newest entries are kept")
        self.assertLessEqual(len(record.sudo().layout_prefs.encode()), MAX_PREFS_BYTES)

    def test_rewriting_a_key_makes_it_recent(self):
        self.settings.set_layout_prefs({"columnWidths": {"old": {"n": 100}, "new": {"n": 100}}})
        self.settings.set_layout_prefs({"columnWidths": {"old": {"n": 120}}})
        record = self.env["res.users.settings"]._find_or_create_for_user(self.user)
        keys = list(json.loads(record.sudo().layout_prefs)["columnWidths"])
        self.assertEqual(keys[-1], "old", "a re-touched view must not be the next one pruned")

    def test_blob_is_not_broadcast_with_the_other_settings(self):
        record = self.env["res.users.settings"]._find_or_create_for_user(self.user)
        self.assertNotIn("layout_prefs", record._res_users_settings_format())
