# -*- coding: utf-8 -*-
"""Production-grade test suite for ``custom_accounting_reports``.

Strategy
--------
Each test seeds its own minimal company + chart of accounts (5–10
accounts, two journals, a handful of partners) and posts moves through
the ORM so the resulting ``account.move.line`` rows feed the engine's
raw-SQL aggregator exactly as in production.

We never rely on the demo data — modules in this repo ship without it
(see ``__manifest__.py``).
"""

from __future__ import annotations

from datetime import date, timedelta

from odoo import Command
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCustomReports(TransactionCase):
    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env["account.account"]
        cls.Journal = cls.env["account.journal"]
        cls.Partner = cls.env["res.partner"]
        cls.Move = cls.env["account.move"]

        cls.company = cls.env["res.company"].create(
            {
                "name": "Reports Test Co",
                "currency_id": cls.env.ref("base.IDR").id,
            }
        )
        cls.env.user.write(
            {
                "company_ids": [Command.link(cls.company.id)],
                "company_id": cls.company.id,
            }
        )
        # Re-bind env so subsequent reads honour the new company.
        cls.env = cls.env(user=cls.env.user, su=True).with_company(cls.company)

        cls.acc_cash = cls._mk_account("11000", "Cash", "asset_cash")
        cls.acc_recv = cls._mk_account(
            "11100",
            "Receivables",
            "asset_receivable",
        )
        cls.acc_pay = cls._mk_account(
            "21100",
            "Payables",
            "liability_payable",
        )
        cls.acc_equity = cls._mk_account(
            "31000",
            "Owner Equity",
            "equity",
        )
        cls.acc_revenue = cls._mk_account(
            "41000",
            "Service Revenue",
            "income",
        )
        cls.acc_expense = cls._mk_account(
            "52000",
            "Operating Expense",
            "expense",
        )

        cls.j_misc = cls.Journal.create(
            {
                "name": "Miscellaneous",
                "code": "MISC",
                "type": "general",
                "company_id": cls.company.id,
            }
        )

        cls.j_sale = cls.Journal.create(
            {
                "name": "Sales",
                "code": "SAL",
                "type": "sale",
                "company_id": cls.company.id,
            }
        )

        cls.partner_a = cls.Partner.create({"name": "Customer A"})
        cls.partner_b = cls.Partner.create({"name": "Customer B"})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @classmethod
    def _mk_account(cls, code, name, account_type):
        return cls.Account.create(
            {
                "code": code,
                "name": name,
                "account_type": account_type,
                "company_ids": [Command.link(cls.company.id)],
            }
        )

    def _post_move(
        self,
        lines,
        dt=None,
        partner=None,
        ref=None,
    ):
        """Create + post an ``account.move`` with the given line tuples.

        ``lines`` is ``[(account, debit, credit), ...]``.
        """
        dt = dt or date.today()
        line_vals = []
        for account, debit, credit in lines:
            line_vals.append(
                Command.create(
                    {
                        "account_id": account.id,
                        "name": ref or "test",
                        "debit": debit,
                        "credit": credit,
                        "partner_id": partner.id if partner else False,
                    }
                )
            )
        move = self.Move.create(
            {
                "journal_id": self.j_misc.id,
                "date": dt,
                "company_id": self.company.id,
                "partner_id": partner.id if partner else False,
                "ref": ref,
                "line_ids": line_vals,
            }
        )
        move.action_post()
        return move

    def _filters(self, **overrides):
        today = date.today()
        defaults = {
            "date_from": today.replace(month=1, day=1),
            "date_to": today,
            "company_ids": [self.company.id],
            "journal_ids": [],
            "account_ids": [],
            "partner_ids": [],
            "posted_only": True,
        }
        defaults.update(overrides)
        return defaults

    # ------------------------------------------------------------------
    # 1) Trial balance sums to zero (debit total == credit total).
    # ------------------------------------------------------------------
    def test_trial_balance_zero_sum(self):
        today = date.today()
        # Five balanced moves spanning all six accounts.
        self._post_move(
            [
                (self.acc_cash, 1000.0, 0.0),
                (self.acc_equity, 0.0, 1000.0),
            ],
            dt=today,
            ref="m1",
        )
        self._post_move(
            [
                (self.acc_recv, 500.0, 0.0),
                (self.acc_revenue, 0.0, 500.0),
            ],
            dt=today,
            partner=self.partner_a,
            ref="m2",
        )
        self._post_move(
            [
                (self.acc_cash, 500.0, 0.0),
                (self.acc_recv, 0.0, 500.0),
            ],
            dt=today,
            partner=self.partner_a,
            ref="m3",
        )
        self._post_move(
            [
                (self.acc_expense, 200.0, 0.0),
                (self.acc_cash, 0.0, 200.0),
            ],
            dt=today,
            ref="m4",
        )
        self._post_move(
            [
                (self.acc_expense, 100.0, 0.0),
                (self.acc_pay, 0.0, 100.0),
            ],
            dt=today,
            partner=self.partner_b,
            ref="m5",
        )

        tb = self.env["custom.report.trial.balance"]
        lines = tb._build_lines(self._filters())
        grand = next(l for l in lines if l.get("type") == "grand_total")
        self.assertAlmostEqual(
            grand["movement_debit"],
            grand["movement_credit"],
            places=2,
            msg="Trial-balance debit total must equal credit total.",
        )
        self.assertGreater(
            grand["movement_debit"],
            0.0,
            "Trial balance must aggregate non-zero movement.",
        )

    # ------------------------------------------------------------------
    # 2) Aged receivable: 4 invoices spread across all 5 buckets.
    #    Buckets defined in custom_report_aged_receivable.BUCKETS.
    # ------------------------------------------------------------------
    def test_aged_receivable_buckets(self):
        today = date.today()
        cases = [
            # (days_overdue, amount, expected_bucket_code)
            (-5, 100.0, "not_due"),  # due in the future
            (10, 200.0, "d_0_30"),  # 1..30
            (45, 300.0, "d_31_60"),  # 31..60
            (80, 400.0, "d_61_90"),  # 61..90
            (200, 500.0, "d_91_180"),  # 91..180
        ]
        partners = []
        for i, (overdue, amount, _bucket) in enumerate(cases):
            partner = self.Partner.create({"name": f"Aging P{i}"})
            partners.append(partner)
            due = today - timedelta(days=overdue)
            move = self.Move.create(
                {
                    "journal_id": self.j_misc.id,
                    "date": today - timedelta(days=max(overdue, 0)),
                    "invoice_date_due": due,
                    "company_id": self.company.id,
                    "partner_id": partner.id,
                    "line_ids": [
                        Command.create(
                            {
                                "account_id": self.acc_recv.id,
                                "name": "aging",
                                "debit": amount,
                                "credit": 0.0,
                                "partner_id": partner.id,
                                "date_maturity": due,
                            }
                        ),
                        Command.create(
                            {
                                "account_id": self.acc_revenue.id,
                                "name": "aging",
                                "debit": 0.0,
                                "credit": amount,
                                "partner_id": partner.id,
                            }
                        ),
                    ],
                }
            )
            move.action_post()

        ar = self.env["custom.report.aged.receivable"]
        result = ar._build_lines(self._filters())
        per_partner = {r["partner_name"]: r for r in result["rows"]}

        for i, (_overdue, amount, expected_bucket) in enumerate(cases):
            row = per_partner.get(f"Aging P{i}")
            self.assertIsNotNone(
                row,
                f"Partner P{i} must appear in aged receivable.",
            )
            self.assertAlmostEqual(
                row[expected_bucket],
                amount,
                places=2,
                msg=(f"Partner P{i}: expected {amount} in bucket {expected_bucket}, got {row[expected_bucket]}."),
            )

    # ------------------------------------------------------------------
    # 3) General Ledger respects the partner filter.
    # ------------------------------------------------------------------
    def test_general_ledger_partner_filter(self):
        today = date.today()
        self._post_move(
            [
                (self.acc_recv, 1000.0, 0.0),
                (self.acc_revenue, 0.0, 1000.0),
            ],
            dt=today,
            partner=self.partner_a,
            ref="A1",
        )
        self._post_move(
            [
                (self.acc_recv, 2000.0, 0.0),
                (self.acc_revenue, 0.0, 2000.0),
            ],
            dt=today,
            partner=self.partner_b,
            ref="B1",
        )

        gl = self.env["custom.report.general.ledger"]
        lines = gl._build_lines(self._filters(partner_ids=[self.partner_a.id]))
        # Find Receivables account section.
        ar_section = next(
            (l for l in lines if l.get("type") == "account" and l.get("account_code") == "11100"),
            None,
        )
        self.assertIsNotNone(
            ar_section,
            "Receivables section must appear in filtered GL.",
        )
        # Every line in the section must reference Customer A only.
        for entry in ar_section["lines"]:
            self.assertEqual(
                entry.get("partner"),
                self.partner_a.name,
                "Partner filter must exclude other partners.",
            )

    # ------------------------------------------------------------------
    # 4) Balance Sheet equation: assets = liabilities + equity (+/- P&L).
    # ------------------------------------------------------------------
    def test_balance_sheet_equation(self):
        today = date.today()
        # Owner contributes 10_000 cash.
        self._post_move(
            [
                (self.acc_cash, 10000.0, 0.0),
                (self.acc_equity, 0.0, 10000.0),
            ],
            dt=today,
            ref="contrib",
        )
        # Borrows 3_000.
        self._post_move(
            [
                (self.acc_cash, 3000.0, 0.0),
                (self.acc_pay, 0.0, 3000.0),
            ],
            dt=today,
            ref="borrow",
        )
        # Earns 2_000 revenue.
        self._post_move(
            [
                (self.acc_recv, 2000.0, 0.0),
                (self.acc_revenue, 0.0, 2000.0),
            ],
            dt=today,
            partner=self.partner_a,
            ref="sale",
        )
        # Pays 500 expense.
        self._post_move(
            [
                (self.acc_expense, 500.0, 0.0),
                (self.acc_cash, 0.0, 500.0),
            ],
            dt=today,
            ref="opex",
        )

        bs = self.env["custom.report.balance.sheet"]
        lines = bs._build_lines(self._filters())

        total_assets = next(l for l in lines if l.get("type") == "total" and l.get("label") == "Total Assets")[
            "signed_balance"
        ]
        total_liab = next(l for l in lines if l.get("type") == "total" and l.get("label") == "Total Liabilities")[
            "signed_balance"
        ]
        total_eq = next(l for l in lines if l.get("type") == "total" and l.get("label") == "Total Equity")[
            "signed_balance"
        ]

        # The accounting equation (Assets = Liab + Equity) holds only
        # when the period P&L is closed into equity. Until close, the
        # gap equals net profit / (loss). Verify directly.
        pl = self.env["custom.report.profit.loss"]
        pl_lines = pl._build_lines(self._filters())
        net_profit = next(l for l in pl_lines if l.get("type") == "grand_total")["signed_balance"]

        self.assertAlmostEqual(
            total_assets - total_liab - total_eq,
            net_profit,
            places=2,
            msg=("Assets - (Liab + Equity) must equal Net Profit before period close."),
        )

    # ------------------------------------------------------------------
    # 5) Tax report subtotals per fiscal position sum to grand total.
    # ------------------------------------------------------------------
    def test_tax_report_subtotals(self):
        """Even with no posted tax in the test period, the invariant
        ``sum(category.tax_subtotal) == grand_total.tax_amount`` must
        hold. We post one PPN out + one PPh-23 line to exercise both
        the 'output' and 'withholding' branches.
        """
        today = date.today()
        # PPN Out 11% (sale side).
        ppn = self.env["account.tax"].create(
            {
                "name": "PPN Out 11%",
                "amount": 11.0,
                "type_tax_use": "sale",
                "company_id": self.company.id,
            }
        )
        # PPh 23 (purchase side, withholding by convention).
        pph = self.env["account.tax"].create(
            {
                "name": "PPh 23 2%",
                "amount": 2.0,
                "type_tax_use": "purchase",
                "company_id": self.company.id,
            }
        )
        # Post one move with each tax to seed both base + tax lines.
        for tax in (ppn, pph):
            self.Move.create(
                {
                    "journal_id": self.j_misc.id,
                    "date": today,
                    "company_id": self.company.id,
                    "line_ids": [
                        Command.create(
                            {
                                "account_id": self.acc_revenue.id,
                                "name": f"base {tax.name}",
                                "debit": 0.0,
                                "credit": 1000.0,
                                "tax_ids": [Command.link(tax.id)],
                            }
                        ),
                        Command.create(
                            {
                                "account_id": self.acc_cash.id,
                                "name": f"cash {tax.name}",
                                "debit": 1000.0,
                                "credit": 0.0,
                            }
                        ),
                    ],
                }
            )  # left as draft on purpose — we still want the engine
        # Run the tax report unrestricted to posted_only so unposted
        # entries are aggregated for the test.
        report = self.env["custom.report.tax"]
        lines = report._build_lines(self._filters(posted_only=False))
        grand = next(
            (l for l in lines if l.get("type") == "grand_total"),
            None,
        )
        self.assertIsNotNone(grand, "Tax report must emit a grand_total.")
        category_subtotal = sum(l["tax_subtotal"] for l in lines if l.get("type") == "category")
        self.assertAlmostEqual(
            category_subtotal,
            grand["tax_amount"],
            places=2,
            msg="Category subtotals must sum to grand tax_amount.",
        )

    # ------------------------------------------------------------------
    # 6) General Ledger flat layout: one row per line, account as a column,
    #    column picker honoured.
    # ------------------------------------------------------------------
    def test_general_ledger_flat_layout(self):
        today = date.today()
        self._post_move(
            [(self.acc_recv, 1000.0, 0.0), (self.acc_revenue, 0.0, 1000.0)],
            dt=today,
            partner=self.partner_a,
            ref="F1",
        )

        gl_all = self.env["custom.report.general.ledger"].with_context(gl_layout="flat")
        lines = gl_all._build_lines(self._filters())
        detail = [l for l in lines if l.get("type") != "grand_total"]
        self.assertTrue(detail, "Flat GL must emit per-line rows.")
        self.assertTrue(
            all("account_code" in l for l in detail),
            "Flat GL rows must carry the account as a field/column.",
        )
        self.assertEqual(lines[-1].get("type"), "grand_total")

        # No optional columns selected -> 9 core columns only.
        gl_core = self.env["custom.report.general.ledger"].with_context(gl_layout="flat", gl_columns=[])
        self.assertEqual(len(gl_core._xlsx_columns()), 9)
        # All optional columns selected -> 9 core + 10 optional = 19.
        gl_full = self.env["custom.report.general.ledger"].with_context(
            gl_layout="flat",
            gl_columns=[
                "doc_no",
                "reference",
                "tax",
                "clearing",
                "cost_center",
                "profit_center",
                "currency",
                "amount_currency",
                "due_date",
                "user",
            ],
        )
        self.assertEqual(len(gl_full._xlsx_columns()), 19)
        # Grouped layout keeps the legacy 7-column spec.
        gl_grouped = self.env["custom.report.general.ledger"]
        self.assertEqual(len(gl_grouped._xlsx_columns()), 7)

    # ------------------------------------------------------------------
    # 7) Aged receivable detail: one row per open document, grouped by
    #    partner.
    # ------------------------------------------------------------------
    def test_aged_receivable_detail(self):
        today = date.today()
        partner = self.Partner.create({"name": "DetailP"})
        due = today - timedelta(days=10)
        move = self.Move.create(
            {
                "journal_id": self.j_misc.id,
                "date": today - timedelta(days=10),
                "invoice_date_due": due,
                "company_id": self.company.id,
                "partner_id": partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.acc_recv.id,
                            "name": "detail aging",
                            "debit": 250.0,
                            "credit": 0.0,
                            "partner_id": partner.id,
                            "date_maturity": due,
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.acc_revenue.id,
                            "name": "detail aging",
                            "debit": 0.0,
                            "credit": 250.0,
                            "partner_id": partner.id,
                        }
                    ),
                ],
            }
        )
        move.action_post()

        ar = self.env["custom.report.aged.receivable"].with_context(aging_detail=True)
        result = ar._build_lines(self._filters())
        self.assertEqual(result.get("type"), "aging_detail")
        grp = next(g for g in result["partners"] if g["partner_name"] == "DetailP")
        self.assertEqual(len(grp["rows"]), 1, "One open document expected.")
        row = grp["rows"][0]
        self.assertEqual(row["doc_no"], move.name)
        self.assertAlmostEqual(row["d_0_30"], 250.0, places=2)
        self.assertAlmostEqual(grp["subtotal"]["total"], 250.0, places=2)

    # ------------------------------------------------------------------
    # 8) Kartu Utang / Kartu Piutang: side-restricted partner cards.
    # ------------------------------------------------------------------
    def test_partner_cards(self):
        today = date.today()
        self._post_move(
            [(self.acc_recv, 700.0, 0.0), (self.acc_revenue, 0.0, 700.0)],
            dt=today,
            partner=self.partner_a,
            ref="AR1",
        )
        self._post_move(
            [(self.acc_expense, 400.0, 0.0), (self.acc_pay, 0.0, 400.0)],
            dt=today,
            partner=self.partner_b,
            ref="AP1",
        )

        rc = self.env["custom.report.receivable.card"]
        r_lines = rc._build_lines(self._filters())
        r_grand = next(l for l in r_lines if l.get("type") == "grand_total")
        self.assertAlmostEqual(r_grand["total_debit"], 700.0, places=2)

        pc = self.env["custom.report.payable.card"]
        p_lines = pc._build_lines(self._filters())
        p_grand = next(l for l in p_lines if l.get("type") == "grand_total")
        self.assertAlmostEqual(p_grand["total_credit"], 400.0, places=2)

    # ------------------------------------------------------------------
    # 9) Uang Muka ledger: auto-detects advance accounts by name.
    # ------------------------------------------------------------------
    def test_advance_report(self):
        today = date.today()
        adv = self._mk_account("11910", "Uang Muka Pembelian", "asset_current")
        self._post_move(
            [(adv, 150.0, 0.0), (self.acc_cash, 0.0, 150.0)],
            dt=today,
            partner=self.partner_a,
            ref="ADV1",
        )

        rep = self.env["custom.report.advance"]
        lines = rep._build_lines(self._filters())  # empty account_ids -> auto-detect
        acct = next(
            (l for l in lines if l.get("type") == "account" and l.get("account_code") == "11910"),
            None,
        )
        self.assertIsNotNone(acct, "Advance account must be auto-detected by name.")
        self.assertAlmostEqual(acct["total_debit"], 150.0, places=2)

    # ------------------------------------------------------------------
    # 10) Sales register: one row per invoice line, totals net of refunds.
    # ------------------------------------------------------------------
    def test_sales_report(self):
        today = date.today()
        inv = self.Move.create(
            {
                "move_type": "out_invoice",
                "journal_id": self.j_sale.id,
                "partner_id": self.partner_a.id,
                "invoice_date": today,
                "date": today,
                "company_id": self.company.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Service line",
                            "quantity": 2.0,
                            "price_unit": 300.0,
                            "account_id": self.acc_revenue.id,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        inv.action_post()

        rep = self.env["custom.report.sales"]
        lines = rep._build_lines(self._filters())
        grand = next(l for l in lines if l.get("type") == "grand_total")
        self.assertAlmostEqual(grand["untaxed"], 600.0, places=2)
        self.assertAlmostEqual(grand["quantity"], 2.0, places=2)
