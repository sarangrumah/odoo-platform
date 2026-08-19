# -*- coding: utf-8 -*-
"""``vat`` and ``x_custom_npwp`` are one number, stored in 16-digit form.

The bug this guards: an operator corrects the Tax ID on the partner form, the
custom NPWP field keeps the old value, and every Coretax / e-Faktur export —
which reads the custom field — keeps emitting the superseded NPWP.
"""

from __future__ import annotations

from .common import TaxIdCommon


class TestNpwpVatSync(TaxIdCommon):
    def test_vat_write_updates_npwp(self):
        p = self.Partner.create({"name": "Test", "vat": "1015556667008000"})
        self.assertEqual(p.x_custom_npwp, "1015556667008000")
        p.vat = "1000000006490833"
        self.assertEqual(p.x_custom_npwp, "1000000006490833")

    def test_npwp_write_updates_vat(self):
        p = self.Partner.create({"name": "Test", "x_custom_npwp": "1000000006490833"})
        self.assertEqual(p.vat, "1000000006490833")

    def test_vat_wins_when_both_written(self):
        p = self.Partner.create({"name": "Test"})
        p.write({"vat": "1000000006490833", "x_custom_npwp": "1015556667008000"})
        self.assertEqual(p.vat, "1000000006490833")
        self.assertEqual(p.x_custom_npwp, "1000000006490833")

    def test_legacy_15_digit_padded_to_16(self):
        p = self.Partner.create({"name": "Test", "vat": "023110679073000"})
        self.assertEqual(p.vat, "0023110679073000")
        self.assertEqual(p.x_custom_npwp, "0023110679073000")

    def test_separators_stripped(self):
        p = self.Partner.create({"name": "Test", "x_custom_npwp": "01.234.567.8-901.234"})
        self.assertEqual(p.vat, "0012345678901234")
        self.assertEqual(p.x_custom_npwp, "0012345678901234")

    def test_foreign_vat_left_alone(self):
        # A non-Indonesian VAT number is not an NPWP and must not be mirrored.
        p = self.Partner.create({"name": "Test", "vat": "GB123456789"})
        self.assertEqual(p.vat, "GB123456789")
        self.assertFalse(p.x_custom_npwp)

    def test_clearing_one_side_clears_the_other(self):
        p = self.Partner.create({"name": "Test", "vat": "1000000006490833"})
        p.vat = False
        self.assertFalse(p.x_custom_npwp)

    def test_coretax_npwp_falls_back_to_vat(self):
        p = self.Partner.create({"name": "Test"})
        # Simulate a pre-sync database: only the Tax ID carries the number.
        self.env.cr.execute(
            "UPDATE res_partner SET vat=%s, x_custom_npwp=NULL WHERE id=%s",
            ("1000000006490833", p.id),
        )
        p.invalidate_recordset()
        self.assertEqual(p._custom_coretax_npwp(), "1000000006490833")
        self.assertEqual(p._custom_coretax_nitku(), "1000000006490833000000")

    def test_company_pemotong_guard_accepts_vat_only(self):
        company = self.env.company
        self.env.cr.execute(
            "UPDATE res_partner SET vat=%s, x_custom_npwp=NULL WHERE id=%s",
            ("1000000006490833", company.partner_id.id),
        )
        company.partner_id.invalidate_recordset()
        self.assertEqual(
            company._check_coretax_pemotong(require_signer=False),
            "1000000006490833",
        )
