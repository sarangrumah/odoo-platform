# -*- coding: utf-8 -*-
"""FK/OF row building: the two invariants Coretax validates on the written cells.

``HARGA_TOTAL - DISKON == DPP`` per OF row, and FK totals equal the sum of the
OF column beneath them. Both used to be broken — DISKON was a flat zero, and the
money columns were unrounded floats.
"""

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged

# Column offsets, so an assertion reads as the column it checks.
OF_HARGA_SATUAN = 5
OF_JUMLAH_BARANG = 6
OF_HARGA_TOTAL = 7
OF_DISKON = 8
OF_CHECK_DPP_LAIN = 9
OF_DPP = 10
OF_DPP_LAIN = 11
OF_PPN = 13

FK_KD_JENIS = 3
FK_MASA = 6
FK_TAHUN = 7
FK_JUMLAH_DPP = 17
FK_JUMLAH_DPP_LAIN = 18
FK_JUMLAH_PPN = 19


@tagged("post_install", "-at_install", "custom_coretax_export")
class TestCoretaxFkRows(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.builder = cls.env["custom.coretax.fk.builder"].sudo()
        cls.company = cls.company_data["company"]
        cls.company.partner_id.x_custom_npwp = "0012345678901000"
        cls.company.x_custom_nitku_suffix = "000000"
        cls.product = cls.env["product.product"].create({"name": "Barang FK", "type": "consu"})

        # PPN 12% on a PMK 131/2024 nilai-lain base of 11/12 — the combination
        # the client's reference workbook is cut from.
        cls.ppn_nilai_lain = (
            cls.env["account.tax"]
            .sudo()
            .create(
                {
                    "name": "PPN 12% (DPP Nilai Lain)",
                    "amount_type": "percent",
                    "amount": 12.0,
                    "type_tax_use": "sale",
                    "company_id": cls.company.id,
                    "x_custom_dpp_method": "nilai_lain",
                    "x_custom_dpp_factor": 11.0 / 12.0,
                }
            )
        )

    def _invoice(self, lines, invoice_date="2026-08-03"):
        return (
            self.env["account.move"]
            .sudo()
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": invoice_date,
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "quantity": line.get("qty", 1),
                                "price_unit": line["price"],
                                "discount": line.get("discount", 0.0),
                                "tax_ids": [(6, 0, self.ppn_nilai_lain.ids)],
                            },
                        )
                        for line in lines
                    ],
                }
            )
        )

    def _rows(self, moves):
        _headers, rows = self.builder._coretax_fk_rows(moves, company=self.company)
        return rows

    @staticmethod
    def _split(rows):
        return (
            [r for r in rows if r[0] == "FK"],
            [r for r in rows if r[0] == "OF"],
        )

    # ------------------------------------------------- DISKON / HARGA_TOTAL

    def test_reference_row_matches_client_workbook(self):
        """The exact row from the client's sample: 340.000 x 5, 20% discount."""
        invoice = self._invoice([{"price": 340000.0, "qty": 5, "discount": 20.0}])
        invoice.action_post()
        _fk, of_rows = self._split(self._rows(invoice))

        self.assertEqual(of_rows[0][OF_HARGA_SATUAN], 340000.0)
        self.assertEqual(of_rows[0][OF_JUMLAH_BARANG], 5)
        self.assertEqual(of_rows[0][OF_HARGA_TOTAL], 1700000.0)
        self.assertEqual(of_rows[0][OF_DISKON], 340000.0)
        self.assertEqual(of_rows[0][OF_DPP], 1360000.0)

    def test_discount_invariant_holds_on_every_row(self):
        invoice = self._invoice(
            [
                {"price": 340000.0, "qty": 5, "discount": 20.0},
                {"price": 125000.0, "qty": 3, "discount": 7.5},
                {"price": 99000.0, "qty": 11},
            ]
        )
        invoice.action_post()
        _fk, of_rows = self._split(self._rows(invoice))

        self.assertEqual(len(of_rows), 3)
        for row in of_rows:
            self.assertEqual(
                row[OF_HARGA_TOTAL] - row[OF_DISKON],
                row[OF_DPP],
                "HARGA_TOTAL - DISKON must equal DPP on %s" % (row,),
            )

    def test_undiscounted_line_still_writes_zero_diskon(self):
        """Regression guard: the fix must not invent a discount out of nothing."""
        invoice = self._invoice([{"price": 100000.0, "qty": 2}])
        invoice.action_post()
        _fk, of_rows = self._split(self._rows(invoice))

        self.assertEqual(of_rows[0][OF_DISKON], 0.0)
        self.assertEqual(of_rows[0][OF_HARGA_TOTAL], 200000.0)

    # ------------------------------------------------------------- rounding

    def test_round_and_plug_reproduces_reference(self):
        third = 3740000.0 / 3.0
        written, total = self.builder._round_and_plug([third, third, third], 1.0)
        self.assertEqual(written, [1246666.0, 1246666.0, 1246668.0])
        self.assertEqual(total, 3740000.0)
        self.assertEqual(sum(written), total)

    def test_round_and_plug_edge_cases(self):
        self.assertEqual(self.builder._round_and_plug([], 1.0), ([], 0.0))

        written, total = self.builder._round_and_plug([1234.4], 1.0)
        self.assertEqual(written, [1234.0])
        self.assertEqual(total, 1234.0)

        # Already on the grid: the plug must be a no-op, not a nudge.
        written, total = self.builder._round_and_plug([100.0, 200.0, 300.0], 1.0)
        self.assertEqual(written, [100.0, 200.0, 300.0])
        self.assertEqual(total, 600.0)

        # Negatives (a credit-style line) must still tie.
        written, total = self.builder._round_and_plug([-33.4, -33.3, -33.3], 1.0)
        self.assertEqual(sum(written), total)

    def test_fk_totals_equal_of_sums(self):
        """Three equal lines on a nilai-lain tax — the case that used to drift."""
        invoice = self._invoice(
            [
                {"price": 340000.0, "qty": 5, "discount": 20.0},
                {"price": 340000.0, "qty": 5, "discount": 20.0},
                {"price": 340000.0, "qty": 5, "discount": 20.0},
            ]
        )
        invoice.action_post()
        fk_rows, of_rows = self._split(self._rows(invoice))
        fk = fk_rows[0]

        self.assertEqual(sum(r[OF_DPP] for r in of_rows), fk[FK_JUMLAH_DPP])
        self.assertEqual(sum(r[OF_DPP_LAIN] for r in of_rows), fk[FK_JUMLAH_DPP_LAIN])
        self.assertEqual(sum(r[OF_PPN] for r in of_rows), fk[FK_JUMLAH_PPN])

        # And the residual really does land on the last line, as in the sample:
        # three identical lines, so the first two match and the last carries
        # whatever rounding left over. (The absolute figures follow the tax
        # master's stored DPP factor, which is a 6-decimal field — hence the
        # structural assertion rather than the reference workbook's literals,
        # which assume an exact 11/12. Those are pinned in
        # test_round_and_plug_reproduces_reference instead.)
        lains = [r[OF_DPP_LAIN] for r in of_rows]
        self.assertEqual(lains[0], lains[1])
        self.assertEqual(lains[2], fk[FK_JUMLAH_DPP_LAIN] - lains[0] - lains[1])
        self.assertGreaterEqual(lains[2], lains[0])

    def test_grid_is_the_file_format_not_the_ledger(self):
        """Whole rupiah even though the ledger currency carries two decimals.

        Odoo ships IDR with a rounding of 0.01 and both production tenants keep
        it that way, so taking the grid from ``currency.rounding`` would emit
        decimals Coretax does not accept.
        """
        self.assertNotEqual(self.company.currency_id.rounding, 1.0)
        invoice = self._invoice([{"price": 1234.567, "qty": 3}])
        invoice.action_post()
        _fk, of_rows = self._split(self._rows(invoice))
        self.assertEqual(of_rows[0][OF_DPP] % 1, 0.0)

    def test_every_of_amount_is_a_whole_rupiah(self):
        invoice = self._invoice([{"price": 333333.0, "qty": 7, "discount": 3.0}])
        invoice.action_post()
        _fk, of_rows = self._split(self._rows(invoice))
        for column in (OF_HARGA_TOTAL, OF_DISKON, OF_DPP, OF_DPP_LAIN, OF_PPN):
            self.assertEqual(of_rows[0][column] % 1, 0.0)

    # --------------------------------------------------- per-invoice period

    def test_masa_tahun_derived_per_invoice(self):
        march = self._invoice([{"price": 100000.0}], invoice_date="2026-03-15")
        july = self._invoice([{"price": 100000.0}], invoice_date="2026-07-02")
        (march | july).action_post()

        fk_rows, _of = self._split(self._rows(march | july))
        self.assertEqual(
            [(r[FK_MASA], r[FK_TAHUN]) for r in fk_rows],
            [("03", "2026"), ("07", "2026")],
        )

    def test_legacy_wizard_still_emits_its_own_period(self):
        """The masa-pajak wizard's output must not shift under the refactor."""
        invoice = self._invoice([{"price": 100000.0}], invoice_date="2026-08-03")
        invoice.action_post()
        wizard = (
            self.env["custom.coretax.template.export.wizard"]
            .sudo()
            .create(
                {
                    "template": "fk",
                    "masa_pajak": "08",
                    "tahun_pajak": 2026,
                    "company_id": self.company.id,
                }
            )
        )
        _headers, rows = wizard._rows_fk()
        fk_rows, _of = self._split(rows)
        self.assertTrue(fk_rows)
        for row in fk_rows:
            self.assertEqual((row[FK_MASA], row[FK_TAHUN]), ("08", "2026"))

    def test_kd_jenis_transaksi_is_04_on_nilai_lain(self):
        invoice = self._invoice([{"price": 100000.0}])
        invoice.action_post()
        fk_rows, of_rows = self._split(self._rows(invoice))
        self.assertEqual(of_rows[0][OF_CHECK_DPP_LAIN], "Y")
        self.assertEqual(fk_rows[0][FK_KD_JENIS], "04")
