# -*- coding: utf-8 -*-
"""A returned item must gross up Sales Return, never Gross Sales.

The reclass used to resolve its counterparty as Gross Sales-<cat> for every
discounted line, return or not. So a returned item did two wrong things at once:
Sales Return kept the amount NET of the discount (what the client reported), and
Gross Sales was grossed up by a discount on revenue it never earned.

Worked example, one item sold at 100 with 20 discount and returned:

    core     Dr Sales Return    80
    here     Dr Sales Return    20
                Cr Sales Discount  20   -> Sales Return 100, Sales Discount -20

Sales are unchanged:

    core     Cr Gross Sales     80
    here     Dr Sales Discount  20
                Cr Gross Sales     20   -> Gross Sales 100, Sales Discount 20
"""

from odoo.tests.common import TransactionCase

GROSS_SALES, SALES_DISCOUNT, SALES_RETURN = 101, 202, 303


class TestReclassLegs(TransactionCase):
    def setUp(self):
        super().setUp()
        self.legs = self.env["pos.session"]._ri_reclass_legs

    def test_sale_debits_discount_and_credits_gross_sales(self):
        debit, credit, amount = self.legs(GROSS_SALES, SALES_DISCOUNT, False, 20.0)
        self.assertEqual((debit, credit, amount), (SALES_DISCOUNT, GROSS_SALES, 20.0))

    def test_return_debits_sales_return_and_credits_discount(self):
        """X24DN signs a return's discount negative; the magnitude is what posts."""
        debit, credit, amount = self.legs(SALES_RETURN, SALES_DISCOUNT, True, -20.0)
        self.assertEqual((debit, credit, amount), (SALES_RETURN, SALES_DISCOUNT, 20.0))

    def test_return_never_touches_gross_sales(self):
        debit, credit, _amount = self.legs(SALES_RETURN, SALES_DISCOUNT, True, -20.0)
        self.assertNotIn(GROSS_SALES, (debit, credit))

    def test_sale_netting_negative_flips_the_legs(self):
        """An exchange can net a category's sale discount negative."""
        debit, credit, amount = self.legs(GROSS_SALES, SALES_DISCOUNT, False, -20.0)
        self.assertEqual((debit, credit, amount), (GROSS_SALES, SALES_DISCOUNT, 20.0))

    def test_return_netting_positive_flips_the_legs(self):
        """The mirror case: a return group that nets to a positive discount."""
        debit, credit, amount = self.legs(SALES_RETURN, SALES_DISCOUNT, True, 20.0)
        self.assertEqual((debit, credit, amount), (SALES_DISCOUNT, SALES_RETURN, 20.0))

    def test_amount_is_always_a_magnitude(self):
        for is_return in (False, True):
            for raw in (20.0, -20.0):
                _d, _c, amount = self.legs(GROSS_SALES, SALES_DISCOUNT, is_return, raw)
                self.assertGreater(amount, 0.0)
