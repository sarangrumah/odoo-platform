# -*- coding: utf-8 -*-
"""Tests for the X101 dual-code translation (PRODUCT CODE <-> PROD SKU).

X101 ships two codes for the same item: the hyphenated ``PRODUCT CODE`` + size that
suppliers are ordered with (``008M8-000010.5``), and the ``PROD SKU`` that Odoo
stores in ``default_code`` (``008M80000010.5``). ``name_search`` translates between
them so a PO spreadsheet quoting the supplier form still resolves.

Half sizes broke that translation: the tail character class was ``[0-9A-Za-z]*``, so
every code carrying a fraction fell through and the import reported "No matching
record found". The tail now admits one fractional part -- and no more, which is what
the malformed-tail test pins.
"""

from __future__ import annotations

from odoo.tests.common import TransactionCase, tagged

from ..models.product_product import _x101_product_code_from_sku, _x101_sku_from_product_code


@tagged("post_install", "-at_install")
class TestX101DualCode(TransactionCase):
    def test_half_size_translates_both_ways(self):
        self.assertEqual(_x101_sku_from_product_code("008M8-000010.5"), "008M80000010.5")
        self.assertEqual(_x101_product_code_from_sku("008M80000010.5"), "008M8-000010.5")

    def test_translation_round_trips(self):
        for code in ("000A9-0005OS", "00501-00002830", "008M8-000010.5", "008M8-00003.5", "000A9-0005"):
            with self.subTest(code=code):
                sku = _x101_sku_from_product_code(code)
                self.assertIsNotNone(sku, f"{code} did not translate")
                self.assertEqual(_x101_product_code_from_sku(sku), code.upper())

    def test_malformed_tail_is_rejected(self):
        """One fraction at most: a bare [0-9A-Za-z.]* tail would accept these."""
        for code in ("ABCDE-1234..", "ABCDE-1234.", "ABCDE-1234.5.5", "ABCDE-12.34AB"):
            with self.subTest(code=code):
                self.assertIsNone(_x101_sku_from_product_code(code))

    def test_name_search_resolves_a_dotted_supplier_code(self):
        # PROD SKU = PRODUCT CODE without the hyphen + "0" + SIZE.
        product = self.env["product.product"].create({"name": "SNEAKER LOW 10.5", "default_code": "ZT79A0000010.5"})
        results = self.env["product.product"].name_search("ZT79A-000010.5", operator="=")
        self.assertEqual([res[0] for res in results], [product.id])

    def test_search_on_the_supplier_code_field(self):
        product = self.env["product.product"].create({"name": "SNEAKER LOW 11.5", "default_code": "ZT79A0000011.5"})
        self.assertEqual(product.x101_product_code, "ZT79A-000011.5")
        found = self.env["product.product"].search([("x101_product_code", "=", "ZT79A-000011.5")])
        self.assertIn(product, found)

    def test_search_survives_the_in_normalisation(self):
        """Odoo 19 rewrites "=" to "in" before the search method sees it."""
        plain = self.env["product.product"].create({"name": "TEE L", "default_code": "ZT79B00010L"})
        half = self.env["product.product"].create({"name": "SNEAKER 12.5", "default_code": "ZT79B0001012.5"})
        Product = self.env["product.product"]
        self.assertIn(plain, Product.search([("x101_product_code", "in", ["ZT79B-0001L"])]))
        self.assertIn(half, Product.search([("x101_product_code", "in", ["ZT79B-000112.5"])]))
        both = Product.search([("x101_product_code", "in", ["ZT79B-0001L", "ZT79B-000112.5"])])
        self.assertEqual(both, plain | half)
