# -*- coding: utf-8 -*-
"""Tests for the stuck-import watchdog.

``retail.import.executor.run`` commits ``state='running'`` before the handler starts,
so an import whose handler raises (or whose worker is killed) leaves the row running
forever. That is worse than it sounds: ``find_duplicate`` counts ``running`` as a
successful import, so the same file can never be re-imported either. In Aug-2026 that
pair silently froze prd_levis_begbal's sales for eight days.

What is pinned here: the watchdog flips a genuinely dead run to ``failed`` (making it
both visible and re-importable), and leaves a run that is merely slow alone.
"""

from __future__ import annotations

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStuckImportWatchdog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Log = cls.env["retail.import.log"]
        cls.profile = cls.env.ref("custom_retail_import.profile_levis_x101")

    def _running(self, age_hours, started=True, file_hash="deadbeef"):
        when = fields.Datetime.now() - timedelta(hours=age_hours)
        return self.Log.create(
            {
                "profile_id": self.profile.id,
                "filename": "X24DN.xlsx",
                "file_hash": file_hash,
                "state": "running",
                "imported_at": when,
                "started_at": when if started else False,
            }
        )

    def test_flags_a_dead_run(self):
        log = self._running(age_hours=9)
        self.Log._cron_flag_stuck()
        self.assertEqual(log.state, "failed")
        self.assertTrue(log.finished_at, "a failed run must stop counting duration up forever")
        self.assertIn("stalled", log.error_message or "")

    def test_leaves_a_slow_run_alone(self):
        """X101 takes ~10 minutes; the watchdog must not shoot a run still in flight."""
        log = self._running(age_hours=1)
        self.Log._cron_flag_stuck()
        self.assertEqual(log.state, "running")

    def test_judges_age_on_imported_at_when_started_at_is_missing(self):
        """A row that died before started_at was written is the earliest failure, not an
        excuse to skip it."""
        log = self._running(age_hours=9, started=False)
        self.Log._cron_flag_stuck()
        self.assertEqual(log.state, "failed")

    def test_threshold_is_configurable(self):
        self.env["ir.config_parameter"].sudo().set_param("retail_import.stuck_hours", "24")
        log = self._running(age_hours=9)
        self.Log._cron_flag_stuck()
        self.assertEqual(log.state, "running", "9h must survive a 24h threshold")

    def test_flagging_unblocks_re_import(self):
        """The whole point: once flagged, the dedup guard stops matching that file."""
        log = self._running(age_hours=9, file_hash="cafebabe")
        self.assertTrue(self.Log.find_duplicate("cafebabe"), "running blocks re-import (by design)")
        self.Log._cron_flag_stuck()
        self.assertEqual(log.state, "failed")
        self.assertFalse(
            self.Log.find_duplicate("cafebabe"),
            "a dead run must not keep the file locked out of the next poll",
        )
