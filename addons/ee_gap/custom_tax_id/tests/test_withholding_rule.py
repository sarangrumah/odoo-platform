# -*- coding: utf-8 -*-
"""Rule resolution + effective-tarif logic."""

from __future__ import annotations

from .common import TaxIdCommon


class TestWithholdingRule(TaxIdCommon):
    def test_resolve_returns_rule_when_product_matches(self):
        bill = self._make_vendor_bill(self.vendor_npwp, 1_000_000)
        line = bill.invoice_line_ids[0]
        rule = self.Rule._resolve_for_line(line)
        # Product carries x_custom_withholding_category_id but our resolver
        # uses product CATEGORY, not the wh category on product. The seeded
        # rule doesn't restrict by category so it should match.
        self.assertEqual(rule, self.rule_konsultan)

    def test_resolve_skips_foreign_only_when_domestic(self):
        # Build a foreign-only rule
        cat = self.env.ref("custom_tax_id.cat_pph26_jasa")
        r_foreign = self.Rule.create(
            {
                "name": "PPh 26 LN",
                "category_id": cat.id,
                "tarif": 20.0,
                "foreign_only": True,
                "priority": 80,
                "account_id": self.hutang_pph_23.id,
                "active": True,
            }
        )
        bill = self._make_vendor_bill(self.vendor_npwp, 1_000_000)
        rule = self.Rule._resolve_for_line(bill.invoice_line_ids[0])
        # Should still pick the konsultan rule, not the foreign-only one
        self.assertEqual(rule, self.rule_konsultan)

    def test_resolve_picks_foreign_rule_for_foreign_partner(self):
        cat = self.env.ref("custom_tax_id.cat_pph26_jasa")
        r_foreign = self.Rule.create(
            {
                "name": "PPh 26 LN",
                "category_id": cat.id,
                "tarif": 20.0,
                "foreign_only": True,
                "priority": 80,
                "account_id": self.hutang_pph_23.id,
                "active": True,
            }
        )
        bill = self._make_vendor_bill(self.vendor_foreign, 1_000_000)
        rule = self.Rule._resolve_for_line(bill.invoice_line_ids[0])
        self.assertEqual(rule, r_foreign)

    def test_effective_tarif_npwp_vs_no_npwp(self):
        self.assertEqual(self.rule_konsultan._effective_tarif(self.vendor_npwp), 2.0)
        self.assertEqual(self.rule_konsultan._effective_tarif(self.vendor_no_npwp), 4.0)

    def test_resolve_returns_empty_for_sales_invoice(self):
        # Sales invoice → no withholding applies on our side
        sale = self.Move.create(
            {
                "move_type": "out_invoice",
                "partner_id": self.vendor_npwp.id,
            }
        )
        sale_line = self.env["account.move.line"]
        # No invoice line yet — _resolve_for_line should handle gracefully
        rule = self.Rule._resolve_for_line(sale_line)
        self.assertFalse(rule)
