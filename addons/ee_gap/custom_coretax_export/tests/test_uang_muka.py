# -*- coding: utf-8 -*-
"""Down payments in the FK record.

FG_UANG_MUKA used to be hard-coded '0', so a faktur uang muka went to Coretax
looking like an ordinary sale.

The deduction Odoo puts on the settlement invoice used to be exported as an OF
item row with quantity -1 and negative amounts, which the importer rejects. It
is now netted off the item rows: the down payment carries a faktur of its own,
so the settlement faktur reports only what is left to pay and says nothing about
the earlier faktur. A 300 juta sale prepaid 50% therefore settles on a 150 juta
faktur, not on a 300 juta one with a 150 juta UANG_MUKA_* deduction.
"""

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged

FK_JUMLAH_DPP = 17
FK_JUMLAH_DPP_LAIN = 18
FK_JUMLAH_PPN = 19
FK_FG_UANG_MUKA = 22
FK_NOMOR_FAKTUR_UM = 23
FK_UANG_MUKA_DPP = 24
FK_UANG_MUKA_DPP_LAIN = 25
FK_UANG_MUKA_PPN = 26

OF_NAMA = 3
OF_HARGA_SATUAN = 5
OF_JUMLAH_BARANG = 6
OF_HARGA_TOTAL = 7
OF_DISKON = 8
OF_DPP = 10


@tagged("post_install", "-at_install", "custom_coretax_export")
class TestCoretaxUangMuka(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.builder = cls.env["custom.coretax.fk.builder"]
        cls.company = cls.company_data["company"]
        cls.company.partner_id.x_custom_npwp = "0012345678901000"
        cls.company.x_custom_nitku_suffix = "000000"
        cls.service = cls.env["product.product"].create(
            {"name": "Jasa Drone", "type": "service", "invoice_policy": "order"}
        )
        # The FK money grid is whole rupiah, so the amounts have to be big
        # enough to survive it — a 1.00 list price would round every
        # down payment to zero and make the ties meaningless.
        cls.price = 300000000.0
        cls.tax_11 = cls.env["account.tax"].create(
            {
                "name": "PPN 11% (test)",
                "amount_type": "percent",
                "amount": 11.0,
                "type_tax_use": "sale",
                "company_id": cls.company.id,
            }
        )

    def _order(self):
        order = (
            self.env["sale.order"]
            .sudo()
            .create(
                {
                    "partner_id": self.partner_a.id,
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.service.id,
                                "product_uom_qty": 1,
                                "price_unit": self.price,
                                "tax_ids": [(6, 0, self.tax_11.ids)],
                            },
                        )
                    ],
                }
            )
        )
        order.action_confirm()
        return order

    def _downpayment_invoice(self, order):
        wizard = (
            self.env["sale.advance.payment.inv"]
            .sudo()
            .with_context(active_ids=order.ids, active_model="sale.order")
            .create({"advance_payment_method": "percentage", "amount": 50.0})
        )
        return wizard._create_invoices(order)

    def _rows(self, invoice, date="2026-07-03"):
        if not invoice.invoice_date:
            invoice.invoice_date = date
        if invoice.state != "posted":
            invoice.action_post()
        _headers, rows = self.builder._coretax_fk_rows(invoice, company=self.company)
        fk_row = next(r for r in rows if r[0] == "FK")
        return fk_row, [r for r in rows if r[0] == "OF"]

    def _fk_flag(self, invoice):
        return self._rows(invoice)[0][FK_FG_UANG_MUKA]

    def _settled(self, nsfp="0400026002695334"):
        """(down-payment invoice, settlement invoice) for one 50%-prepaid order."""
        order = self._order()
        advance = self._downpayment_invoice(order)
        advance.invoice_date = "2026-07-03"
        advance.action_post()
        advance.x_custom_nsfp = nsfp
        wizard = (
            self.env["sale.advance.payment.inv"]
            .sudo()
            .with_context(active_ids=order.ids, active_model="sale.order")
            .create({"advance_payment_method": "delivered"})
        )
        final = wizard._create_invoices(order)
        final.invoice_date = "2026-08-21"
        final.action_post()
        return advance, final

    def test_down_payment_invoice_is_flagged(self):
        invoice = self._downpayment_invoice(self._order())
        self.assertEqual(self._fk_flag(invoice), "1")

    def test_ordinary_invoice_is_not_flagged(self):
        invoice = (
            self.env["account.move"]
            .sudo()
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2026-07-03",
                    "invoice_line_ids": [
                        (0, 0, {"product_id": self.service.id, "quantity": 1, "price_unit": self.price})
                    ],
                }
            )
        )
        self.assertEqual(self._fk_flag(invoice), "0")

    def test_settlement_invoice_is_not_flagged(self):
        """The final faktur carries the deducted down payment, but it settles
        goods — flagging it would tell Coretax two down payments were issued."""
        _advance, final = self._settled()
        self.assertEqual(self._fk_flag(final), "0")

    # ----------------------------------------------- settlement nets the DP

    def test_settlement_has_no_negative_of_row(self):
        """The deduction is a ledger device, not an item sold. Coretax rejects a
        negative OF row, and one used to be emitted for every settled order."""
        _advance, final = self._settled()
        _fk_row, of_rows = self._rows(final)
        self.assertEqual(len(of_rows), 1)
        for row in of_rows:
            self.assertGreater(row[OF_JUMLAH_BARANG], 0)
            self.assertGreaterEqual(row[OF_HARGA_TOTAL], 0)
            self.assertGreaterEqual(row[OF_DPP], 0)

    def test_settlement_reports_what_is_left_to_pay(self):
        """The faktur is the invoice: 300 juta prepaid 50% settles at 150 juta,
        in the FK totals and in the OF row alike."""
        advance, final = self._settled()
        fk_row, of_rows = self._rows(final)
        self.assertEqual(fk_row[FK_JUMLAH_DPP], final.amount_untaxed)
        self.assertEqual(fk_row[FK_JUMLAH_PPN], final.amount_tax)
        self.assertEqual(fk_row[FK_JUMLAH_DPP], sum(r[OF_DPP] for r in of_rows))
        self.assertEqual(fk_row[FK_JUMLAH_DPP], self.price - advance.amount_untaxed)

    def test_settlement_row_reads_as_a_price_not_a_discount(self):
        """Netting must shrink HARGA_SATUAN and HARGA_TOTAL with the base — left
        at the gross they would turn the prepayment into a 50% discount."""
        _advance, final = self._settled()
        _fk_row, of_rows = self._rows(final)
        row = of_rows[0]
        self.assertEqual(row[OF_DISKON], 0)
        self.assertEqual(row[OF_HARGA_TOTAL], final.amount_untaxed)
        self.assertEqual(row[OF_HARGA_SATUAN] * row[OF_JUMLAH_BARANG], final.amount_untaxed)

    def test_settlement_says_nothing_about_the_earlier_faktur(self):
        """The down payment was reported on its own faktur; repeating it here
        would file it twice."""
        advance, final = self._settled(nsfp="0400026002695334")
        fk_row, _of_rows = self._rows(final)
        self.assertTrue(advance.x_custom_has_faktur_pajak)
        self.assertEqual(fk_row[FK_NOMOR_FAKTUR_UM], "")
        self.assertEqual(fk_row[FK_UANG_MUKA_DPP], 0)
        self.assertEqual(fk_row[FK_UANG_MUKA_DPP_LAIN], 0)
        self.assertEqual(fk_row[FK_UANG_MUKA_PPN], 0)

    def test_settlement_without_a_faktur_number_still_exports(self):
        """Nothing on the settlement faktur refers to the down-payment faktur,
        so its NSFP is no longer a precondition for exporting the settlement."""
        advance, final = self._settled()
        advance.x_custom_nsfp = False
        fk_row, _of_rows = self._rows(final)
        self.assertEqual(fk_row[FK_JUMLAH_DPP], final.amount_untaxed)

    def test_fully_deducted_settlement_is_refused(self):
        """A settlement that bills nothing is not a faktur. Refuse it by name
        rather than emit a zero FK record Coretax would bounce."""
        order = self._order()
        advance = self._downpayment_invoice(order)
        advance.invoice_date = "2026-07-03"
        advance.action_post()
        wizard = (
            self.env["sale.advance.payment.inv"]
            .sudo()
            .with_context(active_ids=order.ids, active_model="sale.order")
            .create({"advance_payment_method": "delivered"})
        )
        final = wizard._create_invoices(order)
        deduction = final.invoice_line_ids.filtered(lambda l: l.display_type == "product" and l.price_subtotal < 0)
        items = final.invoice_line_ids.filtered(lambda l: l.display_type == "product") - deduction
        deduction.price_unit = sum(items.mapped("price_subtotal"))
        final.invoice_date = "2026-08-21"
        final.action_post()
        with self.assertRaises(UserError) as caught:
            self.builder._coretax_fk_rows(final, company=self.company)
        self.assertIn(final.name, str(caught.exception))

    def test_ordinary_invoice_leaves_the_uang_muka_block_empty(self):
        invoice = (
            self.env["account.move"]
            .sudo()
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2026-07-03",
                    "invoice_line_ids": [
                        (0, 0, {"product_id": self.service.id, "quantity": 1, "price_unit": self.price})
                    ],
                }
            )
        )
        fk_row, _of_rows = self._rows(invoice)
        self.assertEqual(fk_row[FK_NOMOR_FAKTUR_UM], "")
        self.assertEqual(fk_row[FK_UANG_MUKA_DPP], 0)
        self.assertEqual(fk_row[FK_UANG_MUKA_DPP_LAIN], 0)
        self.assertEqual(fk_row[FK_UANG_MUKA_PPN], 0)

    def test_hand_built_deduction_is_still_netted_off(self):
        """ARKA-AIM's fakturs carry is_downpayment but no sale_line_ids — the
        deduction has to be recognised from the line's own flag."""
        _advance, final = self._settled()
        final.button_draft()
        deduction = final.invoice_line_ids.filtered(lambda l: l.display_type == "product" and l.price_subtotal < 0)
        self.assertTrue(deduction)
        deduction.sale_line_ids = [(5, 0, 0)]
        final.action_post()
        fk_row, of_rows = self._rows(final)
        self.assertEqual(len(of_rows), 1)
        self.assertEqual(fk_row[FK_JUMLAH_DPP], final.amount_untaxed)
