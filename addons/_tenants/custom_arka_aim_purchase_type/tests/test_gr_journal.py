# -*- coding: utf-8 -*-
"""Goods-receipt (GR/IR) accrual: receipt books it, the bill relieves it."""

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestArkaGrJournal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].search([("x_doc_code", "!=", False)], limit=1)
        if not cls.company:
            cls.company = cls.env.company
            cls.company.x_doc_code = "TST"
        from ..hooks import post_init_hook

        post_init_hook(cls.env)
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.company.id]))

        # Own accounts and journal, so the test does not depend on which chart
        # the database happens to carry.
        Account = cls.env["account.account"]
        cls.valuation_account = Account.create(
            {
                "name": "ZZ Test Inventory",
                "code": "ZZGR1001",
                "account_type": "asset_current",
                "company_ids": [(4, cls.company.id)],
            }
        )
        cls.grir_account = Account.create(
            {
                "name": "ZZ Test GR/IR Clearing",
                "code": "ZZGR2001",
                "account_type": "liability_current",
                "reconcile": True,
                "company_ids": [(4, cls.company.id)],
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "ZZ Test Stock Journal",
                "code": "ZZSTJ",
                "type": "general",
                "company_id": cls.company.id,
            }
        )
        cls.categ = (
            cls.env["product.category"]
            .with_company(cls.company)
            .create(
                {
                    "name": "ZZ Test Real-Time Goods",
                    "property_valuation": "real_time",
                    "property_stock_valuation_account_id": cls.valuation_account.id,
                    "property_stock_journal": cls.journal.id,
                }
            )
        )
        cls.mapping = cls.env["arka.purchase.account.map"]._get_map(cls.company, "trade")
        cls.mapping.grir_account_id = cls.grir_account.id

        cls.vendor = cls.env["res.partner"].create({"name": "ZZ Test GR Vendor"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "ZZ Test Received Goods",
                "type": "consu",
                "is_storable": True,
                "categ_id": cls.categ.id,
                "standard_price": 100.0,
                "purchase_method": "receive",
            }
        )
        cls.env["ir.config_parameter"].sudo().set_param("custom_arka_aim_purchase_type.suppress_gr_journal", "0")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _make_po(self, purchase_type="trade", qty=4.0, price=250.0):
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
                                "product_qty": qty,
                                "price_unit": price,
                                "name": self.product.name,
                                "date_planned": fields.Datetime.now(),
                            },
                        )
                    ],
                }
            )
        )

    def _receive(self, po):
        po.button_confirm()
        picking = po.picking_ids
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.button_validate()
        return picking

    def _gr_entries(self, picking):
        refs = ["ARKA-GR-VAL:%s" % move_id for move_id in picking.move_ids.ids]
        return self.env["account.move"].search([("ref", "in", refs)])

    def _balance(self, account):
        lines = self.env["account.move.line"].search([("account_id", "=", account.id), ("parent_state", "=", "posted")])
        return sum(lines.mapped("debit")) - sum(lines.mapped("credit"))

    # ------------------------------------------------------------------
    # Receipt side
    # ------------------------------------------------------------------
    def test_receipt_posts_valuation_against_grir(self):
        picking = self._receive(self._make_po())
        entry = self._gr_entries(picking)
        self.assertEqual(len(entry), 1, "one GR entry per received move")
        self.assertEqual(entry.state, "posted")
        self.assertEqual(entry.journal_id, self.journal)
        self.assertEqual(entry.partner_id, self.vendor)
        debit = entry.line_ids.filtered(lambda l: l.debit)
        credit = entry.line_ids.filtered(lambda l: l.credit)
        self.assertEqual(debit.account_id, self.valuation_account)
        self.assertEqual(credit.account_id, self.grir_account)
        self.assertEqual(debit.debit, 1000.0)
        self.assertEqual(credit.credit, 1000.0)

    def test_posting_is_idempotent(self):
        picking = self._receive(self._make_po())
        # Re-running the poster (an upgrade replay, a second _action_done) must
        # not book the accrual twice.
        picking.move_ids._arka_post_gr_journal()
        picking.move_ids._arka_post_gr_journal()
        self.assertEqual(len(self._gr_entries(picking)), 1)

    def test_periodic_category_books_nothing(self):
        self.categ.with_company(self.company).property_valuation = "periodic"
        picking = self._receive(self._make_po())
        self.assertFalse(self._gr_entries(picking))

    def test_switch_off_books_nothing(self):
        self.env["ir.config_parameter"].sudo().set_param("custom_arka_aim_purchase_type.suppress_gr_journal", "1")
        picking = self._receive(self._make_po())
        self.assertFalse(self._gr_entries(picking))

    def test_unmapped_stream_books_nothing(self):
        """No GR/IR account for the stream -> book nothing rather than guess.

        Posting one leg to a guessed account would be worse than posting none:
        the bill would relieve a different account and the clearing would never
        net off.
        """
        self.mapping.grir_account_id = False
        picking = self._receive(self._make_po())
        self.assertFalse(self._gr_entries(picking))

    def test_internal_transfer_books_nothing(self):
        """Only a vendor receipt raises an accrual, never an internal move."""
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company.id)], limit=1)
        picking = (
            self.env["stock.picking"]
            .with_company(self.company)
            .create(
                {
                    "picking_type_id": warehouse.int_type_id.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "location_dest_id": warehouse.wh_output_stock_loc_id.id,
                    "move_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product.id,
                                "product_uom_qty": 1.0,
                                "location_id": warehouse.lot_stock_id.id,
                                "location_dest_id": warehouse.wh_output_stock_loc_id.id,
                            },
                        )
                    ],
                }
            )
        )
        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.button_validate()
        self.assertFalse(self._gr_entries(picking))
        self.assertFalse(
            self.env["account.move"].search([("ref", "in", ["ARKA-GR-RET-VAL:%s" % m for m in picking.move_ids.ids])])
        )

    # ------------------------------------------------------------------
    # Bill side — the accrual has to come back off
    # ------------------------------------------------------------------
    def test_bill_relieves_the_same_grir_account(self):
        opening = self._balance(self.grir_account)
        po = self._make_po()
        self._receive(po)
        self.assertEqual(self._balance(self.grir_account), opening - 1000.0)
        po.action_create_invoice()
        bill = po.invoice_ids
        bill.invoice_date = fields.Date.context_today(self.env.user)
        self.assertEqual(bill.invoice_line_ids.account_id, self.grir_account)
        bill.action_post()
        # Receipt credit and bill debit cancel: the clearing account is flat again.
        self.assertEqual(self._balance(self.grir_account), opening)

    def test_bill_without_receipt_keeps_its_own_account(self):
        """Billed before receiving -> no accrual exists, so nothing to relieve."""
        po = self._make_po()
        po.button_confirm()
        po.order_line.qty_received = 4.0  # invoiced on quantity, never received
        po.action_create_invoice()
        self.assertNotEqual(po.invoice_ids.invoice_line_ids.account_id, self.grir_account)

    # ------------------------------------------------------------------
    # Vendor return
    # ------------------------------------------------------------------
    def test_vendor_return_reverses_the_accrual(self):
        po = self._make_po()
        picking = self._receive(po)
        wizard = self.env["stock.return.picking"].with_company(self.company).create({"picking_id": picking.id})
        for line in wizard.product_return_moves:
            line.quantity = 4.0
        return_picking = self.env["stock.picking"].browse(wizard.action_create_returns()["res_id"])
        for move in return_picking.move_ids:
            move.quantity = move.product_uom_qty
        return_picking.button_validate()
        entry = self.env["account.move"].search(
            [("ref", "in", ["ARKA-GR-RET-VAL:%s" % m for m in return_picking.move_ids.ids])]
        )
        self.assertEqual(len(entry), 1)
        debit = entry.line_ids.filtered(lambda l: l.debit)
        credit = entry.line_ids.filtered(lambda l: l.credit)
        self.assertEqual(debit.account_id, self.grir_account, "the accrual is released")
        self.assertEqual(credit.account_id, self.valuation_account, "the stock goes back out")
        self.assertEqual(debit.debit, 1000.0)
