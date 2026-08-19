# -*- coding: utf-8 -*-
"""The guard on invoicing a POS order, from both sides."""

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install", "custom_pos_tax_id")
class TestPosInvoiceIdentity(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.product = cls.create_product("Kaos", cls.categ_basic, 100_000.0)

    def _order(self, partner=None):
        self.open_new_session()
        order = self.env["pos.order"].create(
            {
                "session_id": self.pos_session.id,
                "company_id": self.company.id,
                "partner_id": partner.id if partner else False,
                "lines": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "qty": 1,
                            "price_unit": 100_000.0,
                            "price_subtotal": 100_000.0,
                            "price_subtotal_incl": 100_000.0,
                        },
                    )
                ],
                "amount_total": 100_000.0,
                "amount_tax": 0.0,
                "amount_paid": 0.0,
                "amount_return": 0.0,
            }
        )
        return order

    def test_anonymous_order_cannot_be_invoiced(self):
        order = self._order()
        with self.assertRaises(UserError) as caught:
            order._generate_pos_order_invoice()
        self.assertIn("identitas pembeli", str(caught.exception))

    def test_partner_without_npwp_cannot_be_invoiced(self):
        partner = self.env["res.partner"].create({"name": "Walk-in tanpa NPWP"})
        order = self._order(partner)
        with self.assertRaises(UserError) as caught:
            order._generate_pos_order_invoice()
        self.assertIn(order.name or order.pos_reference, str(caught.exception))

    def test_partner_with_nik_is_accepted(self):
        """DJP accepts NIK for an individual buyer, so the guard must too."""
        partner = self.env["res.partner"].create({"name": "Pembeli Orang Pribadi", "x_custom_nik": "3171234567890001"})
        order = self._order(partner)
        self.assertFalse(order._pos_tax_identity_missing())

    def test_partner_with_npwp_is_accepted(self):
        partner = self.env["res.partner"].create({"name": "PT Pembeli", "x_custom_npwp": "0012345678901000"})
        order = self._order(partner)
        self.assertFalse(order._pos_tax_identity_missing())

    def test_npwp_is_loaded_into_the_pos_client(self):
        fields = self.env["res.partner"]._load_pos_data_fields(self.config)
        self.assertIn("x_custom_npwp", fields)
