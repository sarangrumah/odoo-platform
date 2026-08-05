# -*- coding: utf-8 -*-
"""Advance ceilings: resolution order, the two hook points, and the
backwards-compatibility lock (enforcement is off unless asked for)."""

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import PettyCashCommon


@tagged("post_install", "-at_install")
class TestAdvanceLimits(PettyCashCommon):
    def test_off_is_the_default_and_never_blocks(self):
        """The upgrade must not change behaviour for tenants that had no
        limits — a seeded type carries limit_enforcement='off'."""
        self.assertEqual(self.type_ca.limit_enforcement, "off")
        self.type_ca.limit_per_request = 100.0
        request = self._new_request(999_999.0)
        request.action_submit()
        self.assertEqual(request.state, "to_approve")

    def test_block_per_request_limit(self):
        self.type_ca.write({"limit_enforcement": "block", "limit_per_request": 500.0})
        request = self._new_request(600.0)
        with self.assertRaises(UserError):
            request.action_submit()
        request.amount_requested = 500.0
        request.action_submit()
        self.assertEqual(request.state, "to_approve")

    def test_warn_posts_a_note_instead_of_raising(self):
        self.type_ca.write({"limit_enforcement": "warn", "limit_per_request": 100.0})
        request = self._new_request(600.0)
        before = len(request.message_ids)
        request.action_submit()
        self.assertEqual(request.state, "to_approve")
        self.assertGreater(len(request.message_ids), before)

    def test_outstanding_ceiling_counts_open_peers(self):
        self.type_ca.write({"limit_enforcement": "block", "limit_outstanding": 1000.0})
        self._full_cycle(800.0)

        over = self._new_request(400.0)
        with self.assertRaises(UserError):
            over.action_submit()

        ok = self._new_request(200.0)
        ok.action_submit()
        self.assertEqual(ok.state, "to_approve")

    def test_approved_peers_count_too(self):
        """Two requests raised the same afternoon must not each slip under
        the ceiling because neither has been disbursed yet."""
        self.type_ca.write({"limit_enforcement": "block", "limit_outstanding": 1000.0})
        first = self._new_request(900.0)
        first.action_submit()
        first.action_approve()
        self.assertEqual(first.state, "approved")

        second = self._new_request(900.0)
        with self.assertRaises(UserError):
            second.action_submit()

    def test_limit_resolution_employee_beats_job_beats_type(self):
        self.type_ca.write({"limit_enforcement": "block", "limit_outstanding": 5000.0})
        request = self._new_request(100.0)
        self.assertEqual(request._pc_outstanding_limit(), 5000.0)

        self.job.pc_advance_limit = 2000.0
        self.assertEqual(request._pc_outstanding_limit(), 2000.0)

        self.employee.pc_advance_limit = 750.0
        self.assertEqual(request._pc_outstanding_limit(), 750.0)

    def test_max_open_requests(self):
        self.type_ca.write({"limit_enforcement": "block", "max_open_requests": 1})
        self._full_cycle(100.0)
        second = self._new_request(100.0)
        with self.assertRaises(UserError):
            second.action_submit()

    def test_block_when_overdue_clears_after_settle(self):
        self.type_ca.write({"limit_enforcement": "block", "block_when_overdue": True})
        first = self._full_cycle(500.0)
        first.realization_deadline = fields.Date.subtract(fields.Date.context_today(first), days=5)

        second = self._new_request(100.0)
        with self.assertRaises(UserError):
            second.action_submit()

        first.action_return_balance()
        first.action_settle()
        self.assertEqual(first.state, "settled")
        second.action_submit()
        self.assertEqual(second.state, "to_approve")

    def test_disburse_is_the_authoritative_gate(self):
        """Clearing submission does not license disbursement.

        Both requests here got through submission while enforcement was off;
        the ceiling only appears afterwards. Disbursement is the moment the
        cash actually leaves, so it must re-check rather than trust the
        earlier pass.
        """
        request = self._new_request(600.0)
        request.action_submit()
        request.action_approve()
        self._full_cycle(600.0)  # peer eats the headroom

        self.type_ca.write({"limit_enforcement": "block", "limit_outstanding": 1000.0})
        with self.assertRaises(UserError):
            request.action_disburse()

    def test_override_group_bypasses(self):
        self.type_ca.write({"limit_enforcement": "block", "limit_per_request": 10.0})
        user = self.env["res.users"].create(
            {
                "name": "CA Override",
                "login": "ca_override_test",
                # Odoo 19 renamed res.users.groups_id -> group_ids.
                "group_ids": [
                    Command.link(self.env.ref("base.group_user").id),
                    Command.link(self.env.ref("custom_petty_cash.group_petty_cash_limit_override").id),
                ],
            }
        )
        request = self._new_request(5000.0)
        request.with_user(user).action_submit()
        self.assertEqual(request.state, "to_approve")
