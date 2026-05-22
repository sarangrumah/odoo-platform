# -*- coding: utf-8 -*-
"""Shared fixtures: vendor + service product + base PPh 23 jasa konsultan rule."""

from __future__ import annotations

from odoo.tests.common import TransactionCase


class TaxIdCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]
        cls.Product = cls.env["product.product"]
        cls.Category = cls.env["tax.withholding.category"]
        cls.Rule = cls.env["tax.withholding.rule"]
        cls.Move = cls.env["account.move"]
        cls.Account = cls.env["account.account"]
        cls.Journal = cls.env["account.journal"]

        cls.company = cls.env.company
        cls.company.country_id = cls.env.ref("base.id")

        # Hutang PPh 23 account
        cls.hutang_pph_23 = cls.Account.create(
            {
                "code": "21320T",
                "name": "Hutang PPh 23 (test)",
                "account_type": "liability_current",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )

        # Vendor partner with NPWP
        cls.vendor_npwp = cls.Partner.create(
            {
                "name": "PT Konsultan Pajak Sejahtera",
                "is_company": True,
                "x_custom_npwp": "012345678901234",  # 15 digits valid
                "country_id": cls.env.ref("base.id").id,
            }
        )
        # Vendor without NPWP
        cls.vendor_no_npwp = cls.Partner.create(
            {
                "name": "PT Tanpa NPWP",
                "is_company": True,
                "country_id": cls.env.ref("base.id").id,
            }
        )
        # Foreign vendor
        cls.vendor_foreign = cls.Partner.create(
            {
                "name": "Foreign Vendor Co",
                "is_company": True,
                "country_id": cls.env.ref("base.us").id,
            }
        )

        # Use the seeded category for jasa konsultan
        cls.category_konsultan = cls.env.ref("custom_tax_id.cat_pph23_jasa_konsultan")

        # Rule: PPh 23 jasa konsultan 2% / 4% no-NPWP
        cls.rule_konsultan = cls.Rule.create(
            {
                "name": "PPh 23 konsultan (test)",
                "category_id": cls.category_konsultan.id,
                "tarif": 2.0,
                "tarif_no_npwp": 4.0,
                "priority": 50,
                "company_id": cls.company.id,
                "account_id": cls.hutang_pph_23.id,
                "active": True,
            }
        )

        # Service product
        cls.product_jasa = cls.Product.create(
            {
                "name": "Jasa Konsultasi",
                "type": "service",
                "x_custom_withholding_category_id": cls.category_konsultan.id,
            }
        )

        # Purchase journal
        cls.purchase_journal = cls.Journal.search(
            [("type", "=", "purchase"), ("company_id", "=", cls.company.id)], limit=1
        ) or cls.Journal.create(
            {
                "name": "Vendor Bills (test)",
                "type": "purchase",
                "code": "VB-T",
                "company_id": cls.company.id,
            }
        )

        # Expense account
        cls.expense_account = cls.Account.create(
            {
                "code": "67000T",
                "name": "Jasa Konsultan (test)",
                "account_type": "expense",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )

    def _make_vendor_bill(self, vendor, amount, product=None):
        return self.Move.create(
            {
                "move_type": "in_invoice",
                "partner_id": vendor.id,
                "journal_id": self.purchase_journal.id,
                "invoice_date": "2026-01-15",
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Jasa konsultasi Jan",
                            "product_id": (product or self.product_jasa).id,
                            "quantity": 1.0,
                            "price_unit": amount,
                            "account_id": self.expense_account.id,
                        },
                    )
                ],
            }
        )
