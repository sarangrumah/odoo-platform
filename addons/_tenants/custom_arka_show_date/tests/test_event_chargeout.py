# -*- coding: utf-8 -*-
"""The cost of a show leaves inventory the moment the show's revenue is recognised."""

from datetime import date

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install", "custom_arka_show_date")
class TestArkaEventChargeout(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.company.x_custom_event_tracking_enabled = True

        Account = cls.env["account.account"]
        cls.inventory = Account.create(
            {
                "name": "ZZ Show Inventory",
                "code": "ZZCO1001",
                "account_type": "asset_current",
                "company_ids": [(4, cls.company.id)],
            }
        )
        cls.grir = Account.create(
            {
                "name": "ZZ Show GR/IR",
                "code": "ZZCO2001",
                "account_type": "liability_current",
                "reconcile": True,
                "company_ids": [(4, cls.company.id)],
            }
        )
        cls.expense = Account.create(
            {
                "name": "ZZ Show Cost",
                "code": "ZZCO6001",
                "account_type": "expense_direct_cost",
                "company_ids": [(4, cls.company.id)],
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {"name": "ZZ Show Stock", "code": "ZZSHW", "type": "general", "company_id": cls.company.id}
        )
        cls.company.account_stock_journal_id = cls.journal
        # The charge-out reads the inventory accounts off the real-time
        # categories, exactly as the goods receipt writes them.
        cls.categ = (
            cls.env["product.category"]
            .with_company(cls.company)
            .create(
                {
                    "name": "ZZ Show Goods",
                    "property_valuation": "real_time",
                    "property_stock_valuation_account_id": cls.inventory.id,
                    "property_account_expense_categ_id": cls.expense.id,
                    "property_stock_journal": cls.journal.id,
                }
            )
        )
        # A date no real show falls on, so a run against a tenant clone cannot
        # collide with the client's own events (the accounts are shared).
        cls.show = date(2026, 3, 11)
        cls.sale = (
            cls.env["sale.order"]
            .with_company(cls.company)
            .sudo()
            .create(
                {
                    "partner_id": cls.partner_a.id,
                    "company_id": cls.company.id,
                    "x_custom_show_date": cls.show,
                    "x_custom_event_name": "ZZ Test Show",
                    "x_custom_event_location": "ZZ Venue",
                    "order_line": [(0, 0, {"product_id": cls.product_a.id, "product_uom_qty": 1})],
                }
            )
        )
        cls.event = cls.sale._custom_event_analytic_account()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _accrue(self, amount, distribution=None, when=None):
        """A goods receipt, as the purchase module books it."""
        analytic = distribution or {str(self.event.id): 100.0}
        entry = (
            self.env["account.move"]
            .with_company(self.company)
            .create(
                {
                    "move_type": "entry",
                    "journal_id": self.journal.id,
                    "company_id": self.company.id,
                    "date": when or date(2026, 3, 1),
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "account_id": self.inventory.id,
                                "name": "GR",
                                "debit": amount,
                                "credit": 0.0,
                                "analytic_distribution": analytic,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "account_id": self.grir.id,
                                "name": "GR",
                                "debit": 0.0,
                                "credit": amount,
                                "analytic_distribution": analytic,
                            },
                        ),
                    ],
                }
            )
        )
        entry._post(soft=False)
        return entry

    def _invoice(self, amount=5000.0, when=None):
        """A customer invoice that recognises the show's revenue."""
        invoice = (
            self.env["account.move"]
            .with_company(self.company)
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "company_id": self.company.id,
                    "invoice_date": when or date(2026, 3, 15),
                    "date": when or date(2026, 3, 15),
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product_a.id,
                                "quantity": 1,
                                "price_unit": amount,
                                "tax_ids": [],
                                "analytic_distribution": {str(self.event.id): 100.0},
                            },
                        ),
                    ],
                }
            )
        )
        invoice.action_post()
        return invoice

    def _chargeouts(self):
        return self.env["account.move"].search([("ref", "=", "ARKA-SHOWCOST:%s" % self.event.id)])

    def _balance(self, account):
        self.env.flush_all()
        lines = self.env["account.move.line"].search([("account_id", "=", account.id), ("parent_state", "=", "posted")])
        return sum(lines.mapped("balance"))

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_cost_stays_in_inventory_until_revenue_is_recognised(self):
        self._accrue(1000.0)
        self.assertFalse(self._chargeouts())
        self.assertEqual(self._balance(self.inventory), 1000.0)

    def test_invoicing_the_show_moves_its_cost_to_expense(self):
        self._accrue(1000.0)
        invoice = self._invoice()
        entry = self._chargeouts()
        self.assertEqual(len(entry), 1)
        self.assertEqual(entry.state, "posted")
        self.assertEqual(entry.journal_id, self.journal)
        # Booked in the period of the revenue, not of the receipt.
        self.assertEqual(entry.date, invoice.date)
        debit = entry.line_ids.filtered(lambda l: l.debit)
        credit = entry.line_ids.filtered(lambda l: l.credit)
        self.assertEqual(debit.account_id, self.expense)
        self.assertEqual(credit.account_id, self.inventory)
        self.assertEqual(debit.debit, 1000.0)
        # Both legs carry the event, or the P&L per Event would see only one.
        self.assertEqual(debit.analytic_distribution, {str(self.event.id): 100.0})
        self.assertEqual(credit.analytic_distribution, {str(self.event.id): 100.0})
        self.assertEqual(self._balance(self.inventory), 0.0)

    def test_a_second_invoice_charges_nothing_twice(self):
        self._accrue(1000.0)
        self._invoice()
        self._invoice(amount=250.0, when=date(2026, 3, 20))
        self.assertEqual(len(self._chargeouts()), 1)
        self.assertEqual(self._balance(self.inventory), 0.0)

    def test_a_cost_arriving_after_the_invoice_is_charged_out_at_once(self):
        self._accrue(1000.0)
        self._invoice()
        self._accrue(400.0, when=date(2026, 3, 25))
        entries = self._chargeouts()
        self.assertEqual(len(entries), 2, "the late receipt charges itself out")
        self.assertEqual(sum(entries.mapped("amount_total")), 1400.0)
        self.assertEqual(self._balance(self.inventory), 0.0)

    def test_only_this_events_share_of_a_split_line_is_charged(self):
        other = self.sale.copy({"x_custom_event_name": "ZZ Other Show"})._custom_event_analytic_account()
        self._accrue(1000.0, distribution={str(self.event.id): 60.0, str(other.id): 40.0})
        self._invoice()
        entry = self._chargeouts()
        self.assertEqual(entry.line_ids.filtered(lambda l: l.debit).debit, 600.0)
        # The other show has not been invoiced, so its 400 stays put.
        self.assertEqual(self._balance(self.inventory), 400.0)

    def test_nothing_happens_when_the_company_does_not_track_events(self):
        self.company.x_custom_event_tracking_enabled = False
        self._accrue(1000.0)
        self._invoice()
        self.assertFalse(self._chargeouts())
        self.assertEqual(self._balance(self.inventory), 1000.0)

    def test_a_negative_balance_is_never_charged_back_into_inventory(self):
        """More charged out than accrued -- a reversal -- must not invent an asset."""
        self._accrue(1000.0)
        self._invoice()
        self._accrue(-400.0, when=date(2026, 3, 26))
        self.assertEqual(self._balance(self.inventory), -400.0)
        self.assertEqual(len(self._chargeouts()), 1, "no entry puts the negative back")

    def test_an_event_with_no_inventory_posts_nothing(self):
        self._invoice()
        self.assertFalse(self._chargeouts())
