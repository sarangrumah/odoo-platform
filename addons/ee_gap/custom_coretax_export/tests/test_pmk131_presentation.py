# -*- coding: utf-8 -*-
"""A plain 11% PPN is filed in the PMK 131/2024 form, not as an 11% tariff.

Coretax knows only the statutory 12% rate. The 11% effective rate is expressed
as 12% charged on a "nilai lain" base of 11/12 of the price — which is what the
l10n_id chart books the short way, as a bare 11% tax. The export has to
translate: TARIF_PPN 12, DPP_LAIN 11/12, CHECK_DPP_LAIN 'Y'. The PPN rupiah is
identical either way, so the file still ties to the ledger.
"""

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged

OF_CHECK_DPP_LAIN = 9
OF_DPP = 10
OF_DPP_LAIN = 11
OF_TARIF_PPN = 12
OF_PPN = 13

FK_KD_JENIS = 3
FK_JUMLAH_DPP = 17
FK_JUMLAH_DPP_LAIN = 18
FK_JUMLAH_PPN = 19


@tagged("post_install", "-at_install", "custom_coretax_export")
class TestPmk131Presentation(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.builder = cls.env["custom.coretax.fk.builder"]
        cls.company = cls.company_data["company"]
        cls.company.partner_id.x_custom_npwp = "0012345678901000"
        cls.company.x_custom_nitku_suffix = "000000"
        cls.product = cls.env["product.product"].create({"name": "Barang FK", "type": "consu"})

        def _tax(name, amount):
            return (
                cls.env["account.tax"]
                .sudo()
                .create(
                    {
                        "name": name,
                        "amount_type": "percent",
                        "amount": amount,
                        "type_tax_use": "sale",
                        "company_id": cls.company.id,
                    }
                )
            )

        # What l10n_id actually ships and what both tenants post with: labelled
        # 12%, rated 11, no nilai-lain configuration of its own.
        cls.ppn_11 = _tax("12% (Non-Luxury Good)", 11.0)
        cls.ppn_12 = _tax("PPN 12% Penuh", 12.0)

    def _rows(self, tax, price=1_200_000.0, qty=1):
        move = (
            self.env["account.move"]
            .sudo()
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2026-08-03",
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "quantity": qty,
                                "price_unit": price,
                                "tax_ids": [(6, 0, tax.ids)],
                            },
                        )
                    ],
                }
            )
        )
        move.action_post()
        rows = self.builder._coretax_fk_rows(move, company=self.company)[1]
        return (
            [r for r in rows if r[0] == "FK"][0],
            [r for r in rows if r[0] == "OF"],
            move,
        )

    # ------------------------------------------------------------ 11% path

    def test_check_dpp_lain_is_y_for_11_percent(self):
        _fk, of_rows, _move = self._rows(self.ppn_11)
        self.assertEqual(of_rows[0][OF_CHECK_DPP_LAIN], "Y")

    def test_tarif_is_the_statutory_12_not_11(self):
        _fk, of_rows, _move = self._rows(self.ppn_11)
        self.assertEqual(of_rows[0][OF_TARIF_PPN], 12.0)

    def test_dpp_lain_is_eleven_twelfths_of_dpp(self):
        _fk, of_rows, _move = self._rows(self.ppn_11, price=1_200_000.0)
        self.assertEqual(of_rows[0][OF_DPP], 1_200_000.0)
        self.assertEqual(of_rows[0][OF_DPP_LAIN], 1_100_000.0)

    def test_ppn_still_ties_to_the_ledger(self):
        # 12% x 11/12 == 11%: the presentation changes, the rupiah does not.
        _fk, of_rows, move = self._rows(self.ppn_11, price=1_200_000.0)
        self.assertEqual(of_rows[0][OF_PPN], 132_000.0)
        self.assertEqual(of_rows[0][OF_PPN], move.amount_tax)

    def test_fk_totals_follow_the_of_rows(self):
        fk, of_rows, _move = self._rows(self.ppn_11, price=1_200_000.0)
        self.assertEqual(fk[FK_JUMLAH_DPP], sum(r[OF_DPP] for r in of_rows))
        self.assertEqual(fk[FK_JUMLAH_DPP_LAIN], sum(r[OF_DPP_LAIN] for r in of_rows))
        self.assertEqual(fk[FK_JUMLAH_PPN], sum(r[OF_PPN] for r in of_rows))

    def test_kd_jenis_transaksi_is_04(self):
        # 04 = "Other Tax Base", which is what a nilai-lain base makes it.
        fk, _of, _move = self._rows(self.ppn_11)
        self.assertEqual(fk[FK_KD_JENIS], "04")

    # ------------------------------------------------------------ 12% path

    def test_full_12_percent_stays_a_regular_dpp(self):
        _fk, of_rows, _move = self._rows(self.ppn_12, price=1_200_000.0)
        self.assertEqual(of_rows[0][OF_CHECK_DPP_LAIN], "N")
        self.assertEqual(of_rows[0][OF_TARIF_PPN], 12.0)
        self.assertEqual(of_rows[0][OF_DPP_LAIN], of_rows[0][OF_DPP])
        self.assertEqual(of_rows[0][OF_PPN], 144_000.0)
