# -*- coding: utf-8 -*-
"""The Kode Objek's COA must be the COA the PPh actually credits (T17).

The guard is read-only by design: posting re-syncs the dynamic lines and
recomputes a tax line's account from the repartition line, so re-pointing the
account before ``super()._post()`` would simply be undone. These tests lock
both that the guard fires on a real divergence and that it stays silent when
there is nothing to complain about — which is the state of prd_levis_begbal
today, where every Kode Objek in use already agrees with its rule.
"""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TaxIdCommon


@tagged("post_install", "-at_install")
class TestWithholdingAccountGuard(TaxIdCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_account = cls.Account.create(
            {
                "code": "21321T",
                "name": "Hutang PPh 23 lain (test)",
                "account_type": "liability_current",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        # A negative-amount purchase tax is what this tenant models PPh with.
        cls.pph_tax = cls.env["account.tax"].create(
            {
                "name": "PPh 23 (2%) test",
                "type_tax_use": "purchase",
                "amount_type": "percent",
                "amount": -2.0,
                "company_id": cls.company.id,
            }
        )
        cls.pph_tax.invoice_repartition_line_ids.filtered(
            lambda r: r.repartition_type == "tax"
        ).account_id = cls.hutang_pph_23

    def _bill(self):
        return self.Move.create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor_npwp.id,
                "invoice_date": "2026-09-01",
                "journal_id": self.purchase_journal.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Jasa konsultan",
                            "account_id": self.expense_account.id,
                            "quantity": 1,
                            "price_unit": 1000000.0,
                            "tax_ids": [(6, 0, [self.pph_tax.id])],
                            "x_custom_withholding_category_id": self.category_konsultan.id,
                        },
                    )
                ],
            }
        )

    def test_agreement_posts_without_complaint(self):
        """Rule account == repartition account: nothing to report."""
        bill = self._bill()
        self.assertEqual(bill._custom_withholding_account_mismatches(), [])
        bill.action_post()
        self.assertEqual(bill.state, "posted")

    def test_divergence_is_refused_and_names_both_accounts(self):
        self.rule_konsultan.account_id = self.other_account
        bill = self._bill()
        mismatches = bill._custom_withholding_account_mismatches()
        self.assertEqual(len(mismatches), 1)
        _tax_line, used, target = mismatches[0]
        self.assertEqual(used, self.hutang_pph_23)
        self.assertEqual(target, self.other_account)
        with self.assertRaises(UserError) as caught:
            bill.action_post()
        message = str(caught.exception)
        self.assertIn(self.hutang_pph_23.code, message)
        self.assertIn(self.other_account.code, message)
        self.assertEqual(bill.state, "draft")

    def test_the_switch_turns_it_off(self):
        self.rule_konsultan.account_id = self.other_account
        self.env["ir.config_parameter"].sudo().set_param("custom_tax_id.withholding_account_guard", "0")
        bill = self._bill()
        bill.action_post()
        self.assertEqual(bill.state, "posted")

    def test_a_line_without_a_kode_objek_prescribes_nothing(self):
        self.rule_konsultan.account_id = self.other_account
        bill = self._bill()
        bill.invoice_line_ids.x_custom_withholding_category_id = False
        self.assertEqual(bill._custom_withholding_account_mismatches(), [])

    def test_a_customer_invoice_is_out_of_scope(self):
        self.rule_konsultan.account_id = self.other_account
        invoice = self.Move.create(
            {
                "move_type": "out_invoice",
                "partner_id": self.vendor_npwp.id,
                "invoice_date": "2026-09-01",
                "invoice_line_ids": [
                    (0, 0, {"name": "x", "quantity": 1, "price_unit": 100.0}),
                ],
            }
        )
        self.assertEqual(invoice._custom_withholding_account_mismatches(), [])
