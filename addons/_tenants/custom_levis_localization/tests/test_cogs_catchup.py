# -*- coding: utf-8 -*-
"""COGS catch-up on goods receipt (``levis.cogs.catchup``).

Fixtures mirror ``test_cogs_run``: own CoA, own analytic plan, two stores with
their own ``pos.config``. Here, though, products start with NO cost — the whole
point is that the sale happens first and the receipt reveals the cost after the
fact.
"""

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestCogsCatchup(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.env.user.group_ids |= cls.env.ref("point_of_sale.group_pos_manager")
        cls.env.user.group_ids |= cls.env.ref("stock.group_stock_manager")
        cls.env["ir.config_parameter"].sudo().set_param("custom_levis_localization.cogs_catchup_enabled", "1")

        Account = cls.env["account.account"]
        cls.cogs_textile = Account.create(
            {"name": "COGS-textile", "code": "COGSTX", "account_type": "expense_direct_cost"}
        )
        cls.inv_textile = Account.create(
            {"name": "Inventories-textile", "code": "INVTX", "account_type": "asset_current"}
        )
        cls.categ = cls.env["product.category"].create(
            {
                "name": "Textile",
                "property_account_expense_categ_id": cls.cogs_textile.id,
                "property_stock_valuation_account_id": cls.inv_textile.id,
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {"name": "COGS Journal", "type": "general", "code": "CTCHJ", "company_id": cls.company.id}
        )
        cls.env["ir.config_parameter"].sudo().set_param("custom_levis_localization.cogs_catchup_journal_code", "CTCHJ")

        cls.ou_plan = cls.env["account.analytic.plan"].create({"name": "Operating Unit"})
        cls.wh1 = cls.env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)
        cls.ou1 = cls.env["account.analytic.account"].create(
            {"name": "Store 1", "plan_id": cls.ou_plan.id, "company_id": cls.company.id}
        )
        cls.wh1.l10n_ou_analytic_id = cls.ou1.id
        cls.config1 = cls._make_config(cls.wh1, "POS 1")

        # 11% VAT, included in the purchase price — how this tenant's POs are
        # quoted, and the reason the cost basis is the NET price.
        cls.tax = cls.env["account.tax"].create(
            {
                "name": "PPN 11% incl",
                "amount": 11.0,
                "amount_type": "percent",
                "type_tax_use": "purchase",
                "price_include_override": "tax_included",
                "company_id": cls.company.id,
            }
        )
        cls.vendor = cls.env["res.partner"].create({"name": "Vendor"})
        cls.jeans = cls._make_product("Jeans")
        cls.tee = cls._make_product("Tee")

        cls.today = fields.Date.context_today(cls.env.user)
        cls.month_start = cls.today.replace(day=1)
        cls.month_end = cls.month_start + relativedelta(months=1, days=-1)

    # ------------------------------------------------------------------
    @classmethod
    def _make_config(cls, warehouse, name):
        picking_type = cls.env["stock.picking.type"].search(
            [("warehouse_id", "=", warehouse.id), ("code", "=", "outgoing")], limit=1
        )
        return cls.env["pos.config"].create(
            {"name": name, "company_id": cls.company.id, "picking_type_id": picking_type.id}
        )

    @classmethod
    def _make_product(cls, name):
        # No standard_price: the sale happens before any cost is known.
        return cls.env["product.product"].create(
            {
                "name": name,
                "type": "consu",
                "is_storable": True,
                "categ_id": cls.categ.id,
                "available_in_pos": True,
                "purchase_ok": True,
                "lst_price": 500.0,
            }
        )

    def _sell(self, product, qty, date=None):
        date = date or self.today
        session = self.env["pos.session"].search(
            [("config_id", "=", self.config1.id), ("state", "!=", "closed")], limit=1
        )
        if not session:
            session = self.env["pos.session"].create({"config_id": self.config1.id})
            session.update_stock_at_closing = False
        order = self.env["pos.order"].create(
            {
                "company_id": self.company.id,
                "session_id": session.id,
                "date_order": "%s 10:00:00" % date,
                "amount_tax": 0.0,
                "amount_total": 0.0,
                "amount_paid": 0.0,
                "amount_return": 0.0,
                "lines": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "qty": qty,
                            "price_unit": product.lst_price,
                            "price_subtotal": product.lst_price * qty,
                            "price_subtotal_incl": product.lst_price * qty,
                        },
                    )
                ],
            }
        )
        order.write({"state": "done"})
        return order

    def _receive(self, product, qty, price_unit=111.0, taxes=True):
        """A vendor receipt of ``qty`` at a tax-INCLUDED ``price_unit``."""
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "company_id": self.company.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_qty": qty,
                            "price_unit": price_unit,
                            "tax_ids": [(6, 0, self.tax.ids if taxes else [])],
                        },
                    )
                ],
            }
        )
        order.button_confirm()
        picking = order.picking_ids[:1]
        for move in picking.move_ids:
            move.quantity = qty
            move.picked = True
        picking.button_validate()
        return picking

    def _charges(self, product=None):
        domain = [("company_id", "=", self.company.id)]
        if product:
            domain.append(("product_id", "=", product.id))
        return self.env["levis.cogs.charge"].search(domain)

    def _catchups(self):
        return self.env["levis.cogs.catchup"].search([("company_id", "=", self.company.id)])

    # ------------------------------------------------------------------

    def test_01_receipt_charges_what_was_already_sold(self):
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)

        catchup = self._catchups()
        self.assertEqual(len(catchup), 1)
        # 111 tax-included at 11% -> 100 net, times the 3 units already sold.
        self.assertAlmostEqual(catchup.total_cogs, 300.0, places=2)
        line = catchup.line_ids
        self.assertEqual(line.warehouse_id, self.wh1)
        self.assertEqual(line.analytic_account_id, self.ou1)
        self.assertEqual(line.period_date, self.month_start)

        move = catchup.move_id
        self.assertEqual(move.state, "draft")
        self.assertEqual(move.journal_id, self.journal)
        # The sale month is open, so the cost lands in it — never in the future.
        self.assertEqual(move.date, min(self.month_end, self.today))
        debit = move.line_ids.filtered(lambda line: line.debit)
        credit = move.line_ids.filtered(lambda line: line.credit)
        self.assertEqual(debit.account_id, self.cogs_textile)
        self.assertEqual(credit.account_id, self.inv_textile)
        # The Operating Unit rides on BOTH legs.
        self.assertEqual(debit.analytic_distribution, {str(self.ou1.id): 100.0})
        self.assertEqual(credit.analytic_distribution, {str(self.ou1.id): 100.0})

    def test_02_only_products_on_the_receipt_are_touched(self):
        self._sell(self.jeans, 3)
        self._sell(self.tee, 4)
        self._receive(self.jeans, 10)

        self.assertFalse(self._charges(self.tee))
        self.assertEqual(sum(self._charges(self.jeans).mapped("quantity")), 3.0)

    def test_03_whole_outstanding_qty_is_charged_not_the_received_qty(self):
        self._sell(self.jeans, 10)
        self._receive(self.jeans, 4)
        self.assertEqual(sum(self._charges(self.jeans).mapped("quantity")), 10.0)
        self.assertAlmostEqual(self._catchups().total_cogs, 1000.0, places=2)

    def test_04_a_second_receipt_does_not_charge_the_same_units_again(self):
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)
        self._receive(self.jeans, 10)

        self.assertEqual(sum(self._charges(self.jeans).mapped("quantity")), 3.0)
        self.assertAlmostEqual(sum(self._catchups().mapped("total_cogs")), 300.0, places=2)

    def test_05_units_sold_after_the_receipt_are_caught_up_by_the_next_one(self):
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)
        self._sell(self.jeans, 2)
        self._receive(self.jeans, 10)

        self.assertAlmostEqual(sum(self._catchups().mapped("total_cogs")), 500.0, places=2)
        # Same booking date, still draft -> one entry, not two.
        self.assertEqual(len(self._catchups().move_id), 1)

    def test_06_closed_month_is_booked_in_the_present(self):
        self.company.l10n_cogs_reported_through = self.month_end
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)

        move = self._catchups().move_id
        self.assertGreater(move.date, self.month_end)
        # The sale month is still what the cost BELONGS to, whatever its date.
        self.assertEqual(self._catchups().line_ids.period_date, self.month_start)

    def test_07_periodic_run_does_not_recharge_what_the_catchup_booked(self):
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)

        run = self.env["levis.cogs.run"].create(
            {
                "company_id": self.company.id,
                "date_from": self.month_start,
                "date_to": self.month_end,
                "journal_id": self.journal.id,
            }
        )
        run.action_compute()
        self.assertFalse(run.line_ids.filtered(lambda line: line.amount))

    def test_08_periodic_run_records_its_own_charges(self):
        # Cost known up front, so the run — not a receipt — recognises it.
        self.tee.with_company(self.company).standard_price = 20.0
        self._sell(self.tee, 5)
        run = self.env["levis.cogs.run"].create(
            {
                "company_id": self.company.id,
                "date_from": self.month_start,
                "date_to": self.month_end,
                "journal_id": self.journal.id,
            }
        )
        run.action_generate_move()
        charge = self._charges(self.tee)
        self.assertEqual(charge.source, "run")
        self.assertEqual(charge.quantity, 5.0)
        self.assertAlmostEqual(charge.amount, 100.0, places=2)
        # And a receipt afterwards finds nothing left to catch up.
        self._receive(self.tee, 5)
        self.assertEqual(len(self._charges(self.tee)), 1)

    def test_09_disabled_by_default(self):
        self.env["ir.config_parameter"].sudo().set_param("custom_levis_localization.cogs_catchup_enabled", "0")
        self._sell(self.jeans, 3)
        self._receive(self.jeans, 10)
        self.assertFalse(self._catchups())

    def test_10_sales_before_the_window_are_left_alone(self):
        # June/July 2026 were charged by hand, without ledger rows: reaching
        # back into them would book their cost a second time.
        self._sell(self.jeans, 3, date=self.month_start - relativedelta(months=2))
        self._receive(self.jeans, 10)
        self.assertFalse(self._catchups())

    def test_11_window_can_be_widened_deliberately(self):
        older = self.month_start - relativedelta(months=2)
        self.env["ir.config_parameter"].sudo().set_param(
            "custom_levis_localization.cogs_catchup_start", fields.Date.to_string(older)
        )
        self._sell(self.jeans, 3, date=older)
        self._receive(self.jeans, 10)
        charge = self._charges(self.jeans)
        self.assertEqual(charge.period_date, older)
        self.assertAlmostEqual(charge.amount, 300.0, places=2)

    def test_12_cost_falls_back_to_standard_price_without_a_po_line(self):
        self._sell(self.jeans, 2)
        self.jeans.with_company(self.company).standard_price = 70.0
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.wh1.in_type_id.id,
                "location_id": self.env.ref("stock.stock_location_suppliers").id,
                "location_dest_id": self.wh1.lot_stock_id.id,
                "company_id": self.company.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.jeans.id,
                            "product_uom_qty": 5.0,
                            "location_id": self.env.ref("stock.stock_location_suppliers").id,
                            "location_dest_id": self.wh1.lot_stock_id.id,
                            "company_id": self.company.id,
                        },
                    )
                ],
            }
        )
        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = 5.0
            move.picked = True
        picking.button_validate()
        self.assertAlmostEqual(self._catchups().total_cogs, 140.0, places=2)
