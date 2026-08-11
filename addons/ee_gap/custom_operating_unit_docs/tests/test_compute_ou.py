# -*- coding: utf-8 -*-
"""Where the unit comes from on each document, and when it must not be overwritten."""

from odoo.tests import tagged

from .common import OperatingUnitDocsCommon


@tagged("post_install", "-at_install")
class TestComputeOperatingUnit(OperatingUnitDocsCommon):
    def test_01_move_from_journal(self):
        move = self.Move.create({"move_type": "entry", "journal_id": self.journal_b.id})
        self.assertEqual(move.operating_unit_id, self.ou_b)

    def test_02_manual_value_is_never_overwritten(self):
        move = self.Move.create(
            {
                "move_type": "entry",
                "journal_id": self.journal_a.id,
                "operating_unit_id": self.ou_ho.id,
            }
        )
        self.assertEqual(move.operating_unit_id, self.ou_ho)
        move.write({"journal_id": self.journal_b.id})
        self.assertEqual(move.operating_unit_id, self.ou_ho, "an explicit unit survives a journal change")

    def test_03_line_inherits_the_move(self):
        move = self._make_move(self.ou_b, journal=self.journal_b)
        account = self.env["account.account"].search([("company_ids", "in", self.company.id)], limit=1)
        move.write(
            {
                "line_ids": [
                    (0, 0, {"account_id": account.id, "balance": 100.0}),
                    (0, 0, {"account_id": account.id, "balance": -100.0}),
                ]
            }
        )
        self.assertTrue(move.line_ids)
        self.assertEqual(set(move.line_ids.mapped("operating_unit_id")), {self.ou_b})

    def test_04_line_from_analytic_distribution(self):
        """The Levi's shape: the unit rides on the analytic distribution."""
        plan = self.env["account.analytic.plan"].create({"name": "Operating Unit Test"})
        analytic = self.env["account.analytic.account"].create(
            {"name": "Store B analytic", "plan_id": plan.id, "company_id": self.company.id}
        )
        self.ou_b.analytic_account_id = analytic.id

        line_model = self.env["account.move.line"]
        index = self.OU._analytic_index()
        # Odoo joins several plans' ids into one comma-separated key.
        self.assertEqual(line_model._ou_from_distribution({"%s,999" % analytic.id: 100}, index), self.ou_b.id)
        self.assertFalse(line_model._ou_from_distribution({"999": 100}, index))

    def test_05_picking_from_warehouse(self):
        picking_type = self.env["stock.picking.type"].search(
            [("warehouse_id", "=", self.wh_b.id), ("code", "=", "outgoing")], limit=1
        )
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
            }
        )
        self.assertEqual(picking.operating_unit_id, self.ou_b)

    def test_06_purchase_order_and_its_bill(self):
        picking_type = self.env["stock.picking.type"].search(
            [("warehouse_id", "=", self.wh_a.id), ("code", "=", "incoming")], limit=1
        )
        partner = self.env["res.partner"].create({"name": "OU Vendor"})
        order = self.env["purchase.order"].create({"partner_id": partner.id, "picking_type_id": picking_type.id})
        self.assertEqual(order.operating_unit_id, self.ou_a)
        self.assertEqual(order._prepare_invoice().get("operating_unit_id"), self.ou_a.id)

    def test_07_sale_order_from_warehouse(self):
        partner = self.env["res.partner"].create({"name": "OU Customer"})
        order = self.env["sale.order"].create({"partner_id": partner.id, "warehouse_id": self.wh_b.id})
        self.assertEqual(order.operating_unit_id, self.ou_b)
        self.assertEqual(order._prepare_invoice().get("operating_unit_id"), self.ou_b.id)

    def test_08_columns_exist_and_are_indexed(self):
        """The pre_init_hook, not the ORM, must have created these."""
        self.env.cr.execute(
            """
            SELECT indexname FROM pg_indexes
             WHERE tablename = 'account_move_line'
               AND indexname = 'account_move_line_operating_unit_id_index'
            """
        )
        self.assertTrue(self.env.cr.fetchone(), "partial index on account_move_line is missing")
