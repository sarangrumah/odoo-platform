# -*- coding: utf-8 -*-
"""The "Kode Objek PPh" picker has to be reachable by its code.

`tax.withholding.category` searched on `name` only, so an operator picking one
of 108 rows had to type a 60-character "jenis penghasilan" sentence. Both the
DJP kode objek pajak (24-104-01) and our internal handle (Z5-AF) now match, and
the code leads the display so the pick can be confirmed without opening it.
"""

from .common import TaxIdCommon


class TestWithholdingCategorySearch(TaxIdCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.jasa_teknik = cls.Category.create(
            {
                "name": "Jasa Teknik",
                "code": "Z5-AF-T",
                "pph_kind": "pph_23",
                "bupot_object_code": "24-104-01",
            }
        )
        cls.no_object_code = cls.Category.create(
            {"name": "Kategori Tanpa Kode Objek", "code": "Z9-ZZ-T", "pph_kind": "pph_23"}
        )

    def _search(self, term):
        return [i for i, _n in self.Category.name_search(term)]

    def test_found_by_bupot_object_code(self):
        self.assertIn(self.jasa_teknik.id, self._search("24-104-01"))

    def test_found_by_internal_code(self):
        self.assertIn(self.jasa_teknik.id, self._search("Z5-AF-T"))

    def test_found_by_name_still(self):
        self.assertIn(self.jasa_teknik.id, self._search("Jasa Teknik"))

    def test_display_name_leads_with_object_code(self):
        self.assertEqual(self.jasa_teknik.display_name, "24-104-01 - Jasa Teknik")

    def test_display_name_falls_back_to_code(self):
        self.assertEqual(self.no_object_code.display_name, "Z9-ZZ-T - Kategori Tanpa Kode Objek")
