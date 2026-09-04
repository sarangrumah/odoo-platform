# -*- coding: utf-8 -*-
"""Down payments in the FK record.

Two things used to go wrong. FG_UANG_MUKA was hard-coded '0', so a faktur uang
muka went to Coretax looking like an ordinary sale. And a settlement faktur
exported its down-payment deduction as an OF item row with quantity -1 and
negative amounts, instead of reporting it in the FK record's UANG_MUKA_* block.
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

OF_JUMLAH_BARANG = 6
OF_HARGA_TOTAL = 7
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

    # ------------------------------------------------- settlement UANG_MUKA_*

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

    def test_settlement_reports_gross_and_deducts_in_fk(self):
        """OF rows carry the full price; the down payment is subtracted through
        the FK block, and the two still tie to what is left to pay."""
        advance, final = self._settled()
        fk_row, of_rows = self._rows(final)
        self.assertEqual(fk_row[FK_JUMLAH_DPP], sum(r[OF_DPP] for r in of_rows))
        self.assertEqual(fk_row[FK_UANG_MUKA_DPP], advance.amount_untaxed)
        self.assertEqual(fk_row[FK_UANG_MUKA_PPN], advance.amount_tax)
        self.assertEqual(fk_row[FK_JUMLAH_PPN] - fk_row[FK_UANG_MUKA_PPN], final.amount_tax)
        self.assertEqual(fk_row[FK_JUMLAH_DPP] - fk_row[FK_UANG_MUKA_DPP], final.amount_untaxed)

    def test_settlement_carries_the_previous_faktur_number(self):
        advance, final = self._settled(nsfp="0400026002695334")
        fk_row, _of_rows = self._rows(final)
        self.assertEqual(fk_row[FK_NOMOR_FAKTUR_UM], "0400026002695334")
        self.assertTrue(advance.x_custom_has_faktur_pajak)

    def test_settlement_without_a_faktur_number_is_refused(self):
        """An empty NOMOR_FAKTUR_UM_SEBELUMNYA beside a non-zero UANG_MUKA_PPN is
        a file Coretax accepts and files wrongly — refuse it by name instead."""
        advance, final = self._settled()
        advance.x_custom_nsfp = False
        with self.assertRaises(UserError) as caught:
            self.builder._coretax_fk_rows(final, company=self.company)
        self.assertIn(advance.name, str(caught.exception))

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

    def test_hand_built_deduction_without_an_order_link_still_resolves(self):
        """ARKA-AIM's fakturs carry is_downpayment but no sale_line_ids — the
        invoice_origin they share is what ties settlement to down payment."""
        advance, final = self._settled()
        final.button_draft()
        deduction = final.invoice_line_ids.filtered(lambda l: l.display_type == "product" and l.price_subtotal < 0)
        self.assertTrue(deduction)
        deduction.sale_line_ids = [(5, 0, 0)]
        final.invoice_origin = advance.invoice_origin
        final.action_post()
        fk_row, of_rows = self._rows(final)
        self.assertEqual(fk_row[FK_NOMOR_FAKTUR_UM], advance.x_custom_nsfp)
        self.assertEqual(len(of_rows), 1)
