# -*- coding: utf-8 -*-
"""Type → account/journal routing, and the request → type → company fallback."""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import PettyCashCommon


@tagged("post_install", "-at_install")
class TestAdvanceType(PettyCashCommon):
    def test_type_routes_to_its_own_account(self):
        ca = self._full_cycle(1000.0, self.type_ca)
        pc = self._full_cycle(500.0, self.type_pc)

        ca_accounts = ca.disburse_move_id.line_ids.mapped("account_id")
        pc_accounts = pc.disburse_move_id.line_ids.mapped("account_id")
        self.assertIn(self.advance_ca, ca_accounts)
        self.assertNotIn(self.advance_pc, ca_accounts)
        self.assertIn(self.advance_pc, pc_accounts)
        self.assertNotIn(self.advance_ca, pc_accounts)
        # ...and through the journal the type names, not a shared default.
        self.assertEqual(ca.disburse_move_id.journal_id, self.bank_journal)
        self.assertEqual(pc.disburse_move_id.journal_id, self.cash_journal)

    def test_request_override_beats_type(self):
        request = self._new_request(1000.0, self.type_ca)
        request.advance_account_id = self.advance_pc
        request.action_submit()
        request.action_approve()
        request.action_disburse()
        self.assertIn(self.advance_pc, request.disburse_move_id.line_ids.mapped("account_id"))

    def test_company_fallback_when_no_type(self):
        """A request with no type still works off the legacy company config —
        this is what keeps pre-0.5.0 tenants running after the upgrade."""
        self.company.write(
            {
                "petty_cash_advance_account_id": self.advance_pc.id,
                "petty_cash_bank_out_journal_id": self.cash_journal.id,
                "petty_cash_expense_journal_id": self.gen_journal.id,
            }
        )
        request = self.env["petty.cash.request"].create(
            {"employee_id": self.employee.id, "amount_requested": 250.0, "advance_type_id": False}
        )
        self.assertFalse(request.advance_type_id)
        request.action_submit()
        request.action_approve()
        request.action_disburse()
        self.assertIn(self.advance_pc, request.disburse_move_id.line_ids.mapped("account_id"))

    def test_missing_config_raises(self):
        self.company.write({"petty_cash_advance_account_id": False, "petty_cash_bank_out_journal_id": False})
        bare = self.env["petty.cash.type"].create({"name": "Bare", "code": "BR", "company_id": self.company.id})
        request = self._new_request(100.0, bare)
        request.action_submit()
        request.action_approve()
        with self.assertRaises(UserError):
            request.action_disburse()

    def test_single_default_per_company(self):
        with self.assertRaises(UserError):
            self.type_pc.is_default = True

    def test_allow_third_party_off_blocks_bill(self):
        self.type_pc.allow_third_party = False
        request = self._full_cycle(1000.0, self.type_pc)
        attachment = self.env["ir.attachment"].create(
            {"name": "inv.pdf", "datas": "cGRm", "mimetype": "application/pdf"}
        )
        realization = self.env["petty.cash.realization"].create(
            {
                "request_id": request.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "line_type": "third_party",
                            "name": "Stationery",
                            "partner_id": self.vendor.id,
                            "account_id": self.expense.id,
                            "price_unit": 100.0,
                            "attachment_ids": [(6, 0, attachment.ids)],
                        },
                    )
                ],
            }
        )
        with self.assertRaises(UserError):
            realization.action_post()
