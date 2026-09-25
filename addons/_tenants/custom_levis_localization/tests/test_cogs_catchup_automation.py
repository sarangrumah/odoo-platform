# -*- coding: utf-8 -*-
"""Catch-up without a user: auto-posting, the nightly sweep, the stale alarm.

The receipt hook already books without anybody opening a menu, but it stops at
a draft entry. These tests cover the two switches that carry it through to a
posted entry, and the sweep that finds cost the receipts never saw.
"""

import logging

from dateutil.relativedelta import relativedelta

from odoo.tests import tagged

from .test_cogs_catchup import CogsCatchupCommon

PARAM_AUTOPOST = "custom_levis_localization.cogs_catchup_autopost"


@tagged("post_install", "-at_install")
class TestCogsCatchupAutomation(CogsCatchupCommon):
    def _set_autopost(self, value):
        self.env["ir.config_parameter"].sudo().set_param(PARAM_AUTOPOST, value)

    # ------------------------------------------------------------------
    # Auto-post at the receipt
    # ------------------------------------------------------------------
    def test_01_draft_is_still_the_default(self):
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)
        self.assertEqual(self._catchups().move_id.state, "draft")

    def test_02_autopost_posts_the_receipt_entry(self):
        self._set_autopost("1")
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)

        catchup = self._catchups()
        self.assertEqual(catchup.move_id.state, "posted")
        self.assertFalse(catchup.post_error)
        # The ledger is written either way: posting is not what stops a unit
        # being charged twice.
        self.assertAlmostEqual(sum(self._charges(self.jeans).mapped("amount")), 300.0, places=2)

    def test_03_autopost_costs_one_entry_per_receipt(self):
        """The price of immediacy, asserted so nobody is surprised by it."""
        self._set_autopost("1")
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)
        self._sell(self.tee, 2)
        self._receive(self.tee, 10)

        catchups = self._catchups()
        self.assertEqual(len(catchups), 2, "a posted entry is never added to")
        self.assertEqual(set(catchups.mapped("move_id.state")), {"posted"})

    def test_04_draft_entries_of_one_day_stay_one_entry(self):
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)
        self._sell(self.tee, 2)
        self._receive(self.tee, 10)
        self.assertEqual(len(self._catchups()), 1)

    # ------------------------------------------------------------------
    # Posting what is due
    # ------------------------------------------------------------------
    def test_05_post_due_leaves_today_alone(self):
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)
        catchup = self._catchups()

        self.assertFalse(self.env["levis.cogs.catchup"]._post_due(self.company))
        self.assertEqual(catchup.move_id.state, "draft", "today may still grow")

        catchup.book_date = self.today - relativedelta(days=1)
        posted = self.env["levis.cogs.catchup"]._post_due(self.company)
        self.assertEqual(posted, catchup)
        self.assertEqual(catchup.move_id.state, "posted")

    def test_06_a_failure_is_recorded_not_raised(self):
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)
        catchup = self._catchups()
        # A lock date over the entry's own date is the everyday reason an entry
        # refuses to post here.
        self.company.fiscalyear_lock_date = self.today + relativedelta(days=1)

        self.assertFalse(catchup._try_post())
        self.assertEqual(catchup.move_id.state, "draft")
        self.assertTrue(catchup.post_error, "the reason must survive on the record")

        self.company.fiscalyear_lock_date = False
        self.assertEqual(catchup._try_post(), catchup)
        self.assertFalse(catchup.post_error, "cleared once it posts")

    def test_07_posting_twice_is_a_no_op(self):
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)
        catchup = self._catchups()
        catchup._try_post()
        self.assertFalse(catchup._try_post(), "an entry is posted once")

    # ------------------------------------------------------------------
    # The nightly sweep
    # ------------------------------------------------------------------
    def test_08_sweep_charges_a_cost_that_arrived_without_a_receipt(self):
        """The case the hook cannot see: the master price was simply corrected."""
        self._sell(self.jeans, 4)
        self.assertFalse(self._charges(self.jeans))

        self.jeans.with_company(self.company).standard_price = 50.0
        swept = self.env["levis.cogs.catchup"]._sweep(self.company)

        self.assertEqual(len(swept), 1)
        self.assertAlmostEqual(sum(self._charges(self.jeans).mapped("amount")), 200.0, places=2)
        self.assertEqual(swept.move_id.state, "draft")

    def test_09_sweep_never_charges_the_same_unit_twice(self):
        self._sell(self.jeans, 4)
        self.jeans.with_company(self.company).standard_price = 50.0
        self.env["levis.cogs.catchup"]._sweep(self.company)

        self.assertFalse(self.env["levis.cogs.catchup"]._sweep(self.company))
        self.assertAlmostEqual(sum(self._charges(self.jeans).mapped("amount")), 200.0, places=2)

    def test_10_sweep_says_so_when_a_unit_has_no_cost_at_all(self):
        """No PO ever carried it, so no receipt can ever reveal its cost."""
        self._sell(self.tee, 5)
        with self.assertLogs("odoo.addons.custom_levis_localization.models.cogs_catchup", logging.WARNING) as logs:
            self.assertFalse(self.env["levis.cogs.catchup"]._sweep(self.company))
        self.assertTrue(any("no cost at all" in line for line in logs.output))
        self.assertFalse(self._charges(self.tee))

    def test_11_cron_sweeps_then_posts(self):
        self._sell(self.jeans, 4)
        self.jeans.with_company(self.company).standard_price = 50.0
        self.env["levis.cogs.catchup"]._sweep(self.company)
        self._catchups().book_date = self.today - relativedelta(days=1)

        self._sell(self.tee, 2)
        self.tee.with_company(self.company).standard_price = 20.0
        self.env["levis.cogs.catchup"]._cron_catch_up()

        catchups = self._catchups()
        self.assertEqual(len(catchups), 2, "yesterday's entry and today's")
        yesterday = catchups.filtered(lambda c: c.book_date < self.today)
        today = catchups - yesterday
        self.assertEqual(yesterday.move_id.state, "posted")
        self.assertEqual(today.move_id.state, "draft", "today is still collecting")
        self.assertAlmostEqual(sum(self._charges(self.tee).mapped("amount")), 40.0, places=2)

    def test_12_cron_does_nothing_while_the_catch_up_is_off(self):
        self.env["ir.config_parameter"].sudo().set_param("custom_levis_localization.cogs_catchup_enabled", "0")
        self._sell(self.jeans, 4)
        self.jeans.with_company(self.company).standard_price = 50.0

        self.env["levis.cogs.catchup"]._cron_catch_up()
        self.assertFalse(self._catchups())

    # ------------------------------------------------------------------
    # The alarm
    # ------------------------------------------------------------------
    def test_13_stale_drafts_are_logged(self):
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)
        catchup = self._catchups()
        catchup.book_date = self.today - relativedelta(days=5)

        with self.assertLogs("odoo.addons.custom_levis_localization.models.cogs_catchup", logging.WARNING) as logs:
            stale = self.env["levis.cogs.catchup"]._warn_stale(self.company)
        self.assertEqual(stale, catchup)
        self.assertTrue(any("unposted" in line for line in logs.output))

    def test_14_a_posted_entry_is_never_stale(self):
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)
        catchup = self._catchups()
        catchup.book_date = self.today - relativedelta(days=5)
        catchup._try_post()
        self.assertFalse(self.env["levis.cogs.catchup"]._warn_stale(self.company))
