# -*- coding: utf-8 -*-
"""The six stock registers (sheet #26, #27, #28, #59, #64, #69, #70).

These run on whatever the database holds, so they assert *shapes and
invariants* rather than figures — a grand total asserted as a constant only
ever held on an empty database, which is how `test_06_asset_register_report`
came to fail on every tenant clone.
"""

from datetime import date

from odoo.tests import TransactionCase, tagged

STOCK_REPORTS = (
    ("stock_movement", "custom.report.stock.movement"),
    ("inventory_summary", "custom.report.inventory.summary"),
    ("inventory_warehouse", "custom.report.inventory.warehouse"),
    ("purchase_return", "custom.report.purchase.return"),
    ("stock_transfer", "custom.report.stock.transfer"),
    ("stock_adjustment", "custom.report.stock.adjustment"),
)


@tagged("post_install", "-at_install")
class TestStockReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dispatch = cls.env["report.custom_accounting_reports.report_dispatch"]

    def _options(self, **extra):
        return {
            "date_from": date(2026, 1, 1),
            "date_to": date(2026, 12, 31),
            "company_ids": self.env.companies.ids,
            "warehouse_ids": [],
            "product_ids": [],
            "categ_ids": [],
            "partner_ids": [],
            "group_by": "none",
            **extra,
        }

    def test_every_code_resolves_to_its_own_model(self):
        """A code missing from REPORT_MODEL_MAP silently prints a Trial Balance."""
        for code, model_name in STOCK_REPORTS:
            self.assertEqual(self.dispatch._report_model(code)._name, model_name, code)

    def test_every_report_builds_and_ends_with_a_grand_total(self):
        for code, model_name in STOCK_REPORTS:
            lines = self.env[model_name]._build_lines(self._options())
            self.assertTrue(lines, code)
            self.assertEqual(lines[-1].get("type"), "grand_total", code)

    def test_the_pdf_renders_from_the_same_column_spec_as_the_xlsx(self):
        """One template serves all six; a divergence here is a silent wrong PDF."""
        for code, model_name in STOCK_REPORTS:
            ctx = self.env[model_name]._compute(self._options())
            self.assertEqual(
                [c["header"] for c in ctx["columns"]],
                [c["header"] for c in self.env[model_name]._xlsx_columns()],
                code,
            )

    def test_every_data_row_carries_every_column(self):
        for code, model_name in STOCK_REPORTS:
            model = self.env[model_name]
            fields_wanted = [c["field"] for c in model._xlsx_columns()]
            rows = [line for line in model._build_lines(self._options()) if not line.get("type")]
            for row in rows[:50]:
                for field in fields_wanted:
                    self.assertIn(field, row, "%s: %s" % (code, field))

    def test_movement_balance_is_per_item_and_per_warehouse(self):
        """A running balance summed across items is not a stock position."""
        model = self.env["custom.report.stock.movement"]
        lines = model._build_lines(self._options())
        rows = [line for line in lines if not line.get("type")]
        if not rows:
            self.skipTest("no stock movement in this database")
        running = {}
        for row in rows:
            key = (row["warehouse"], row["item_code"])
            signed = (row["qty_in"] or 0.0) if row["qty_in"] != "" else (row["qty_out"] or 0.0)
            running[key] = running.get(key, 0.0) + signed
            self.assertAlmostEqual(row["balance"], running[key], places=4)

    def test_summary_arithmetic_closes(self):
        """Beginning + In + Out + Adjustment must equal Ending, by construction."""
        model = self.env["custom.report.inventory.summary"]
        rows = [line for line in model._build_lines(self._options()) if not line.get("type")]
        if not rows:
            self.skipTest("no stock in this database")
        for row in rows[:200]:
            self.assertAlmostEqual(
                row["begin_qty"] + row["in_qty"] + row["out_qty"] + row["adj_qty"],
                row["end_qty"],
                places=4,
            )

    def test_position_report_ties_to_the_summary_ending(self):
        summary = self.env["custom.report.inventory.summary"]._build_lines(self._options())
        position = self.env["custom.report.inventory.warehouse"]._build_lines(self._options(group_by="warehouse"))
        self.assertAlmostEqual(summary[-1].get("end_qty", 0.0), position[-1].get("qty", 0.0), places=2)
        self.assertAlmostEqual(summary[-1].get("end_value", 0.0), position[-1].get("value", 0.0), places=0)

    def test_a_warehouse_filter_can_only_narrow(self):
        model = self.env["custom.report.inventory.warehouse"]
        everything = [r for r in model._build_lines(self._options()) if not r.get("type")]
        if not everything:
            self.skipTest("no stock in this database")
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        narrowed = [r for r in model._build_lines(self._options(warehouse_ids=warehouse.ids)) if not r.get("type")]
        self.assertLessEqual(len(narrowed), len(everything))

    def test_wizards_carry_their_filters(self):
        for model_name, code in (
            ("custom.report.stock.movement.wizard", "stock_movement"),
            ("custom.report.inventory.summary.wizard", "inventory_summary"),
            ("custom.report.inventory.warehouse.wizard", "inventory_warehouse"),
            ("custom.report.purchase.return.wizard", "purchase_return"),
            ("custom.report.stock.transfer.wizard", "stock_transfer"),
            ("custom.report.stock.adjustment.wizard", "stock_adjustment"),
        ):
            wizard = self.env[model_name].create({})
            self.assertEqual(wizard._report_code, code)
            filters = wizard._build_filters()
            for key in ("date_from", "date_to", "company_ids", "warehouse_ids"):
                self.assertIn(key, filters, model_name)
