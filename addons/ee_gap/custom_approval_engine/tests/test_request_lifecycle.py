# -*- coding: utf-8 -*-
"""Approval request state machine + tier walking."""

from __future__ import annotations

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import ApprovalTestCommon


@tagged("post_install", "-at_install")
class TestRequestLifecycle(ApprovalTestCommon):

    def _build_two_tier_matrix(self):
        m = self._make_matrix("Two-tier PO")
        self._add_tier(m, sequence=10, name="Dept Head", approvers=[self.user_approver_a])
        self._add_tier(m, sequence=20, name="Finance", approvers=[self.user_approver_b])
        return m

    def test_submit_then_first_tier_approve_advances(self):
        m = self._build_two_tier_matrix()
        po = self._make_po()
        req = self.Request._create_for_record(po, matrix=m)
        req.action_submit()

        self.assertEqual(req.state, "pending")
        self.assertEqual(req.current_tier_id.name, "Dept Head")
        self.assertIn(self.user_approver_a, req.pending_approver_ids)

        req.with_user(self.user_approver_a).action_approve(comment="ok")
        # Reload from DB (record cache)
        req.invalidate_recordset()

        self.assertEqual(req.state, "pending")
        self.assertEqual(req.current_tier_id.name, "Finance")
        self.assertIn(self.user_approver_b, req.pending_approver_ids)

    def test_final_tier_approve_completes(self):
        m = self._build_two_tier_matrix()
        po = self._make_po()
        req = self.Request._create_for_record(po, matrix=m)
        req.action_submit()
        req.with_user(self.user_approver_a).action_approve()
        req.with_user(self.user_approver_b).action_approve()
        req.invalidate_recordset()

        self.assertEqual(req.state, "approved")
        self.assertTrue(req.decided_at)

    def test_reject_terminates_request(self):
        m = self._build_two_tier_matrix()
        po = self._make_po()
        req = self.Request._create_for_record(po, matrix=m)
        req.action_submit()

        req.with_user(self.user_approver_a).action_reject(comment="missing docs")
        req.invalidate_recordset()

        self.assertEqual(req.state, "rejected")
        self.assertEqual(req.final_decision_user_id, self.user_approver_a)

    def test_non_approver_cannot_approve(self):
        m = self._build_two_tier_matrix()
        po = self._make_po()
        req = self.Request._create_for_record(po, matrix=m)
        req.action_submit()

        with self.assertRaises(UserError):
            req.with_user(self.user_requester).action_approve()

    def test_require_all_waits_for_every_approver(self):
        m = self._make_matrix("Require all")
        self._add_tier(
            m, name="Co-approval",
            approvers=[self.user_approver_a, self.user_approver_b],
            require_all=True,
        )
        po = self._make_po()
        req = self.Request._create_for_record(po, matrix=m)
        req.action_submit()

        # First approver acts — still pending
        req.with_user(self.user_approver_a).action_approve()
        req.invalidate_recordset()
        self.assertEqual(req.state, "pending")

        # Second approver completes
        req.with_user(self.user_approver_b).action_approve()
        req.invalidate_recordset()
        self.assertEqual(req.state, "approved")

    def test_purchase_button_confirm_blocked_until_approved(self):
        m = self._build_two_tier_matrix()
        po = self._make_po()
        # No approval requested yet → mixin gate raises
        with self.assertRaises(UserError):
            po.button_confirm()

        # Request approval, but tier 1 still pending → still blocked
        po.action_request_approval()
        po.invalidate_recordset()
        with self.assertRaises(UserError):
            po.button_confirm()

        # Walk both tiers
        req = po.x_custom_approval_request_id
        req.with_user(self.user_approver_a).action_approve()
        req.with_user(self.user_approver_b).action_approve()
        po.invalidate_recordset()

        # Confirm should now proceed (may still fail on missing lines — that's Odoo core)
        try:
            po.button_confirm()
        except UserError as e:
            # Acceptable if it's about empty order lines, not about approval
            self.assertNotIn("approval", str(e).lower())
