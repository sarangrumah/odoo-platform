# -*- coding: utf-8 -*-
"""Guards against silently losing a reconciliation.

Every case here is drawn from a real July 2026 incident in prd_levis_begbal,
where a month's aged payable stopped tying out to the trial balance because
three payments lost the bills they had been registered against.
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestReconciliationGuards(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.bank_journal = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.company.id)], limit=1
        )
        cls.partner = cls.env["res.partner"].create({"name": "Guard Vendor"})
        cls.product = cls.env["product.product"].create({"name": "Guard Service", "type": "service"})

    def _bill(self, amount, bill_date=None):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner.id,
                "invoice_date": bill_date or date(2026, 7, 1),
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": amount,
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        bill.action_post()
        return bill

    def _register(self, bill):
        """Pay ``bill`` the way an operator does: Register Payment."""
        wizard = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=bill.ids)
            .create({"journal_id": self.bank_journal.id})
        )
        wizard.action_create_payments()
        return self.env["account.payment"].search([("partner_id", "=", self.partner.id)], order="id desc", limit=1)

    # ------------------------------------------------------------------
    # Reset to draft
    # ------------------------------------------------------------------
    def test_reset_to_draft_releases_the_bill(self):
        """Odoo 19's button_draft leaves the partials alive, so the bill keeps
        reading Paid against an entry that is no longer in the trial balance.
        Ours undoes the match first."""
        bill = self._bill(1000.0)
        payment = self._register(bill)
        self.assertEqual(bill.payment_state, "paid")

        payment.move_id.button_draft()

        self.assertEqual(payment.move_id.state, "draft")
        self.assertFalse(
            bill.line_ids.filtered(lambda l: l.matched_debit_ids or l.matched_credit_ids),
            "the bill must not stay matched to a draft entry",
        )
        self.assertNotEqual(bill.payment_state, "paid")
        self.assertAlmostEqual(
            sum(
                bill.line_ids.filtered(lambda l: l.account_id.account_type == "liability_payable").mapped(
                    "amount_residual"
                )
            ),
            -1000.0,
            places=2,
        )

    def test_reset_to_draft_names_what_it_released(self):
        """The operator has to be able to see that resetting cost them the
        application — nothing else in the UI says so."""
        bill = self._bill(500.0)
        payment = self._register(bill)
        before = len(payment.move_id.message_ids)

        payment.move_id.button_draft()

        bodies = payment.move_id.message_ids[: len(payment.move_id.message_ids) - before]
        self.assertTrue(
            any(bill.name in (m.body or "") for m in bodies),
            "the chatter must name the document that was released",
        )

    def test_reset_to_draft_without_reconciliation_is_untouched(self):
        bill = self._bill(300.0)
        self.assertEqual(bill.state, "posted")
        bill.button_draft()
        self.assertEqual(bill.state, "draft")

    # ------------------------------------------------------------------
    # Structural edits on a matched line
    # ------------------------------------------------------------------
    def test_cannot_move_a_matched_line_to_another_account(self):
        """What actually destroyed 8282/2026/07/009: the payable account was
        swapped by hand while the entry sat in draft."""
        bill = self._bill(700.0)
        payment = self._register(bill)
        line = payment.move_id.line_ids.filtered(lambda l: l.account_id.account_type == "liability_payable")
        other = self.env["account.account"].search(
            [
                ("account_type", "=", "liability_payable"),
                ("id", "!=", line.account_id.id),
                ("company_ids", "in", self.company.id),
            ],
            limit=1,
        )
        if not other:
            other = self.env["account.account"].create(
                {
                    "code": "21199",
                    "name": "Other Payables",
                    "account_type": "liability_payable",
                    "company_ids": [(4, self.company.id)],
                }
            )
        with self.assertRaises(UserError):
            line.write({"account_id": other.id})

    def test_no_op_write_on_a_matched_line_is_allowed(self):
        """Odoo rewrites whole line dicts in plenty of places; refusing a write
        that does not actually change the account would block ordinary edits."""
        bill = self._bill(700.0)
        payment = self._register(bill)
        line = payment.move_id.line_ids.filtered(lambda l: l.account_id.account_type == "liability_payable")
        line.write({"account_id": line.account_id.id, "name": "relabelled"})
        self.assertEqual(line.name, "relabelled")

    def test_unmatched_line_can_still_be_moved(self):
        """The guard must bite on matched lines only — reclassifying an ordinary
        open item is everyday work. A plain journal entry, not an invoice, so
        Odoo's invoice-sync machinery is not what is under test here."""
        expenses = self.env["account.account"].search(
            [("account_type", "=", "expense"), ("company_ids", "in", self.company.id)],
            limit=2,
        )
        self.assertEqual(len(expenses), 2, "need two expense accounts to reclassify between")
        journal = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.company.id)], limit=1
        )
        move = self.env["account.move"].create(
            {
                "journal_id": journal.id,
                "date": date(2026, 7, 1),
                "line_ids": [
                    (0, 0, {"account_id": expenses[0].id, "name": "x", "debit": 700.0, "credit": 0.0}),
                    (0, 0, {"account_id": expenses[1].id, "name": "y", "debit": 0.0, "credit": 700.0}),
                ],
            }
        )
        line = move.line_ids.filtered(lambda l: l.account_id == expenses[0])
        self.assertFalse(line.matched_debit_ids or line.matched_credit_ids)
        line.write({"account_id": expenses[1].id})
        self.assertEqual(line.account_id, expenses[1])

    # ------------------------------------------------------------------
    # Duplicate payments
    # ------------------------------------------------------------------
    def test_duplicate_payment_is_refused(self):
        """8282/2026/07/016 and /045: same vendor, same amount, same day, one
        obligation. The first never applied, so the bill still read Not Paid."""
        vals = {
            "partner_id": self.partner.id,
            "partner_type": "supplier",
            "payment_type": "outbound",
            "amount": 250.0,
            "date": date(2026, 7, 14),
            "journal_id": self.bank_journal.id,
        }
        first = self.env["account.payment"].create(vals)
        first.action_post()

        second = self.env["account.payment"].create(dict(vals))
        with self.assertRaises(UserError):
            second.action_post()

    def test_duplicate_payment_posts_once_confirmed(self):
        vals = {
            "partner_id": self.partner.id,
            "partner_type": "supplier",
            "payment_type": "outbound",
            "amount": 250.0,
            "date": date(2026, 7, 14),
            "journal_id": self.bank_journal.id,
        }
        self.env["account.payment"].create(vals).action_post()
        second = self.env["account.payment"].create(dict(vals, duplicate_checked=True))
        second.action_post()
        self.assertIn(second.state, ("in_process", "paid"))

    def test_different_amount_is_not_a_duplicate(self):
        base = {
            "partner_id": self.partner.id,
            "partner_type": "supplier",
            "payment_type": "outbound",
            "date": date(2026, 7, 14),
            "journal_id": self.bank_journal.id,
        }
        self.env["account.payment"].create(dict(base, amount=250.0)).action_post()
        other = self.env["account.payment"].create(dict(base, amount=251.0))
        other.action_post()
        self.assertIn(other.state, ("in_process", "paid"))

    # ------------------------------------------------------------------
    # Unapplied payments
    # ------------------------------------------------------------------
    def test_unapplied_flag_tracks_application(self):
        bill = self._bill(1000.0)
        applied = self._register(bill)
        self.assertFalse(applied.is_unapplied, "a payment that settled a bill is applied")

        standalone = self.env["account.payment"].create(
            {
                "partner_id": self.partner.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "amount": 999.0,
                "date": date(2026, 7, 20),
                "journal_id": self.bank_journal.id,
            }
        )
        standalone.action_post()
        self.assertTrue(
            standalone.is_unapplied,
            "a posted payment that settles nothing must be visible as unapplied",
        )
