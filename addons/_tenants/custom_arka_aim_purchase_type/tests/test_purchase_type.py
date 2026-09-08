# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestArkaPurchaseType(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].search([("x_doc_code", "!=", False)], limit=1)
        if not cls.company:
            # Non-tenant database: give the test company a code so the sequences
            # the hook seeds are the ones under test.
            cls.company = cls.env.company
            cls.company.x_doc_code = "TST"
        from ..hooks import post_init_hook

        post_init_hook(cls.env)
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.company.id]))
        cls.vendor = cls.env["res.partner"].create({"name": "ZZ Test Vendor Non-Trade"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "ZZ Test Waste Bin",
                "type": "consu",
                "is_storable": True,
                "standard_price": 1000.0,
                "purchase_method": "receive",
            }
        )
        cls.group = cls.env["custom.fixed.asset.group"].create(
            {
                "name": "ZZ Test Non-Trade Assets",
                "company_id": cls.company.id,
                "default_useful_life_months": 48,
            }
        )

    def _make_po(self, purchase_type):
        return (
            self.env["purchase.order"]
            .with_company(self.company)
            .create(
                {
                    "partner_id": self.vendor.id,
                    "company_id": self.company.id,
                    "l10n_purchase_type": purchase_type,
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "product_qty": 5.0,
                                "price_unit": 1000.0,
                                "name": self.product.name,
                                "date_planned": fields.Datetime.now(),
                            },
                        )
                    ],
                }
            )
        )

    # ------------------------------------------------------------------
    # Numbering
    # ------------------------------------------------------------------
    def test_trade_and_nontrade_numbering_are_separate_streams(self):
        code = self.company.x_doc_code
        trade = self._make_po("trade")
        non_trade = self._make_po("non_trade")
        self.assertTrue(trade.name.startswith("PO/T/%s/" % code), trade.name)
        self.assertTrue(non_trade.name.startswith("PO/NT/%s/" % code), non_trade.name)
        # Same month, two independent counters -> the tails run on their own.
        second_trade = self._make_po("trade")
        self.assertEqual(
            int(second_trade.name.rsplit("/", 1)[1]),
            int(trade.name.rsplit("/", 1)[1]) + 1,
        )

    def test_number_carries_year_and_month(self):
        today = fields.Date.context_today(self.env.user)
        po = self._make_po("non_trade")
        self.assertIn("/%04d/%02d/" % (today.year, today.month), po.name)

    # ------------------------------------------------------------------
    # Account routing
    # ------------------------------------------------------------------
    def test_bill_inherits_stream_and_payable_account(self):
        mapping = self.env["arka.purchase.account.map"]._get_map(self.company, "non_trade")
        if not mapping.payable_account_id:
            self.skipTest("Non-Trade payable account not present in this chart of accounts")
        po = self._make_po("non_trade")
        po.button_confirm()
        po.order_line.qty_received = 5.0
        po.action_create_invoice()
        bill = po.invoice_ids
        self.assertEqual(bill.l10n_purchase_type, "non_trade")
        payable_line = bill.line_ids.filtered(lambda l: l.display_type == "payment_term")
        self.assertEqual(payable_line.account_id, mapping.payable_account_id)

    def test_trade_and_nontrade_payables_differ(self):
        Map = self.env["arka.purchase.account.map"]
        trade_map = Map._get_map(self.company, "trade")
        nt_map = Map._get_map(self.company, "non_trade")
        if not (trade_map.payable_account_id and nt_map.payable_account_id):
            self.skipTest("Trade/Non-Trade payable accounts not present in this chart of accounts")
        self.assertNotEqual(trade_map.payable_account_id, nt_map.payable_account_id)

    def test_grir_routing_is_inert_for_periodic_categories(self):
        """A periodic category books no receipt accrual, so the bill keeps its
        own account -- routing it to GR/IR would leave the clearing unrelieved."""
        self.product.categ_id.property_valuation = "periodic"
        po = self._make_po("non_trade")
        po.button_confirm()
        po.order_line.qty_received = 5.0
        po.action_create_invoice()
        line = po.invoice_ids.invoice_line_ids
        grir = self.env["arka.purchase.account.map"]._get_map(self.company, "non_trade").grir_account_id
        if grir:
            self.assertNotEqual(line.account_id, grir)

    # ------------------------------------------------------------------
    # Transfer to Asset
    # ------------------------------------------------------------------
    def _receive(self, po):
        po.button_confirm()
        picking = po.picking_ids
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.button_validate()
        return picking

    def test_nontrade_receipt_offers_every_line(self):
        picking = self._receive(self._make_po("non_trade"))
        self.assertEqual(picking.l10n_purchase_type, "non_trade")
        # The product carries no asset flag at all, yet the button is offered.
        self.assertFalse(self.product.product_tmpl_id._asset_conversion_mode())
        self.assertTrue(picking.has_rental_asset_lines)

        wizard = self.env["custom.asset.conversion.wizard"].create({"picking_id": picking.id})
        wizard._populate_lines()
        self.assertEqual(len(wizard.line_ids), 1)
        line = wizard.line_ids
        self.assertTrue(line.selected)
        self.assertEqual(line.conversion_mode, "quantity")
        self.assertEqual(line.quantity, 5.0)
        self.assertEqual(line.subtotal, 5000.0)

    def test_nontrade_conversion_uses_company_default_group(self):
        self.company.x_nontrade_asset_group_id = self.group
        picking = self._receive(self._make_po("non_trade"))
        wizard = self.env["custom.asset.conversion.wizard"].create({"picking_id": picking.id})
        wizard._populate_lines()
        wizard.action_confirm()
        asset = self.env["custom.fixed.asset"].search([("picking_id", "=", picking.id)])
        self.assertEqual(len(asset), 1)
        self.assertEqual(asset.group_id, self.group)
        self.assertEqual(asset.quantity, 5.0)
        self.assertEqual(asset.acquisition_value, 5000.0)
        self.assertEqual(asset.state, "draft")
        # Subledger only: creating the asset must not post anything to the GL.
        self.assertFalse(asset.depreciation_line_ids.filtered("move_id"))

    def test_trade_receipt_is_untouched(self):
        picking = self._receive(self._make_po("trade"))
        self.assertEqual(picking.l10n_purchase_type, "trade")
        self.assertFalse(picking.has_rental_asset_lines)
