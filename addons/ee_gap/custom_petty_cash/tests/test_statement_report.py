# -*- coding: utf-8 -*-
"""Kartu Uang Muka: block shape, running balance, and both registries."""

from datetime import date

from odoo import Command
from odoo.tests import tagged

from .common import PettyCashCommon


@tagged("post_install", "-at_install")
class TestStatementReport(PettyCashCommon):
    def _filters(self):
        return {
            "company_ids": [self.company.id],
            "date_from": date(2000, 1, 1),
            "date_to": date(2999, 12, 31),
            "posted_only": True,
        }

    def _options(self):
        return {
            "company_ids": [self.company.id],
            "date_from": "2000-01-01",
            "date_to": "2999-12-31",
            "posted_only": True,
        }

    def _cycle(self):
        request = self._full_cycle(1000.0)
        self.env["petty.cash.realization"].create(
            {
                "request_id": request.id,
                "line_ids": [
                    Command.create(
                        {
                            "line_type": "expense",
                            "name": "Parking",
                            "account_id": self.expense.id,
                            "price_unit": 600.0,
                        }
                    )
                ],
            }
        ).action_post()
        request.action_return_balance()
        request.action_settle()
        return request

    def test_statement_closes_at_zero(self):
        self._cycle()
        lines = self.env["petty.cash.report.statement"]._build_lines(self._filters())
        blocks = [line for line in lines if line.get("type") == "partner"]
        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertEqual(block["partner_name"], self.employee.name)
        # Disbursement + realization + return.
        self.assertEqual(len(block["lines"]), 3)
        self.assertAlmostEqual(block["closing"], 0.0, 2)
        self.assertAlmostEqual(block["lines"][-1]["running_balance"], 0.0, 2)
        self.assertTrue(any(line.get("type") == "grand_total" for line in lines))

    def test_movements_are_named(self):
        self._cycle()
        lines = self.env["petty.cash.report.statement"]._build_lines(self._filters())
        block = next(line for line in lines if line.get("type") == "partner")
        movements = [row["movement"] for row in block["lines"]]
        self.assertTrue(all(movements), "every row must name what it is")
        self.assertTrue(any("Disbursement" in m for m in movements))
        self.assertTrue(any("Realization" in m for m in movements))
        self.assertTrue(any("Return" in m for m in movements))

    def test_screen_rows_are_not_blank(self):
        """Guards the flattener regression that once made Kartu Utang look
        empty on screen while the XLSX was fine."""
        self._cycle()
        table = self.env["petty.cash.report.statement"].get_report_table(self._options())
        self.assertTrue(table["lines"])
        self.assertTrue(
            any(any(row["values"].values()) for row in table["lines"]),
            "on-screen rows came back blank — check _flatten_for_screen",
        )

    def test_registered_in_both_registries(self):
        """Missing from REPORT_MODEL_MAP and the code silently renders a Trial
        Balance; missing from the t-elif chain and the PDF comes out empty."""
        dispatch = self.env["report.custom_accounting_reports.report_dispatch"]
        model = dispatch._report_model("petty_cash_statement")
        self.assertEqual(model._name, "petty.cash.report.statement")
        self.assertTrue(self.env.ref("custom_petty_cash.report_petty_cash_statement", raise_if_not_found=False))

    def test_xlsx_export_smoke(self):
        self._cycle()
        content = self.env["petty.cash.report.statement"]._xlsx_export(self._filters())
        self.assertTrue(content)

    def test_type_filter(self):
        self._full_cycle(1000.0, self.type_ca)
        filters = dict(self._filters(), advance_type_ids=[self.type_pc.id])
        lines = self.env["petty.cash.report.statement"]._build_lines(filters)
        self.assertFalse([line for line in lines if line.get("type") == "partner"])
