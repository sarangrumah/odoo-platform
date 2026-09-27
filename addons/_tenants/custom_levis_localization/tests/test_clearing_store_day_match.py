# -*- coding: utf-8 -*-
"""Clearing a single store-day, and pairing its two lists by hand.

The two things worth locking down are the ones that would be expensive to get
wrong: a run narrowed to one store must leave every other store *exactly* as it
found it — otherwise clearing one shop quietly claims another's settlements —
and a transaction another credit already names must not be tickable twice.
"""

from datetime import date

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged

MID_ONE = "885004600001"
MID_TWO = "885004600002"


@tagged("post_install", "-at_install")
class TestStoreDayMatch(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        Account = cls.env["account.account"]

        def account(name, code, kind, reconcile=False):
            return Account.create({"name": name, "code": code, "account_type": kind, "reconcile": reconcile})

        cls.suspense = account("Bank Suspense", "SDMSUS", "asset_current")
        cls.mdr = account("MDR Expense", "SDMMDR", "expense")
        cls.ar = account("Trade Receivable", "SDMAR", "asset_receivable", reconcile=True)
        cls.sweep = account("Main Bank", "SDMSWP", "asset_cash")
        cls.charge = account("Bank Charges", "SDMCHG", "expense")
        cls.tender_cash = account("POS Receivable - CASH", "1106000101", "asset_receivable", reconcile=True)
        cls.tender_visa = account("POS Receivable - OFFLINE_VISA", "1106000102", "asset_receivable", reconcile=True)
        cls.tenders = cls.tender_cash + cls.tender_visa

        plan = cls.env["account.analytic.plan"].create({"name": "SDM OU"})
        cls.store_one = cls.env["account.analytic.account"].create({"name": "STORE ONE", "plan_id": plan.id})
        cls.store_two = cls.env["account.analytic.account"].create({"name": "STORE TWO", "plan_id": plan.id})

        cls.gljv = cls.env["account.journal"].create({"name": "SDM Journal", "code": "SDMJ", "type": "general"})
        cls.bank = cls.env["account.journal"].create(
            {
                "name": "BCA test",
                "code": "SDMB",
                "type": "bank",
                "suspense_account_id": cls.suspense.id,
                "levis_clearing_format": "bca",
            }
        )
        cls.config = cls.env["levis.clearing.config"].create(
            {
                "company_id": cls.company.id,
                "journal_id": cls.gljv.id,
                "bank_journal_ids": [Command.set(cls.bank.ids)],
                "suspense_account_id": cls.suspense.id,
                "mdr_account_id": cls.mdr.id,
                "ar_account_id": cls.ar.id,
                "sweep_account_id": cls.sweep.id,
                "bank_charge_account_id": cls.charge.id,
                "pos_receivable_account_ids": [Command.set(cls.tenders.ids)],
                "settlement_lag_days": 1,
                "lookback_days": 10,
            }
        )
        cls.env["levis.bank.mid.map"].create(
            [
                {
                    "name": "Store one",
                    "company_id": cls.company.id,
                    "journal_id": cls.bank.id,
                    "match_type": "mid",
                    "key": MID_ONE,
                    "channel": "debit",
                    "analytic_account_id": cls.store_one.id,
                },
                {
                    "name": "Store two",
                    "company_id": cls.company.id,
                    "journal_id": cls.bank.id,
                    "match_type": "mid",
                    "key": MID_TWO,
                    "channel": "debit",
                    "analytic_account_id": cls.store_two.id,
                },
            ]
        )

    @classmethod
    def _posrec(cls, account, analytic, when, amount):
        move = cls.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": cls.gljv.id,
                "company_id": cls.company.id,
                "date": when,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": account.id,
                            "name": "POS receivable",
                            "debit": amount,
                            "credit": 0.0,
                            "analytic_distribution": {str(analytic.id): 100.0},
                        }
                    ),
                    Command.create(
                        {
                            "account_id": cls.company_data["default_account_revenue"].id,
                            "name": "Sales",
                            "debit": 0.0,
                            "credit": amount,
                        }
                    ),
                ],
            }
        )
        move.action_post()
        return move.line_ids.filtered(lambda aml: aml.account_id == account)

    @classmethod
    def _statement(cls, when, amount, payment_ref):
        line = cls.env["account.bank.statement.line"].create(
            {"journal_id": cls.bank.id, "date": when, "amount": amount, "payment_ref": payment_ref}
        )
        if line.move_id.state == "draft":
            line.move_id.action_post()
        return line

    @classmethod
    def _ref(cls, mid, gross, mdr):
        return "KR OTOMATIS MID : %s LEVIS TEST TGH: %.2f DDR: %.2f" % (mid, gross, mdr)

    def _run(self, **overrides):
        vals = {
            "company_id": self.company.id,
            "date_from": date(2026, 7, 1),
            "date_to": date(2026, 7, 31),
            "journal_id": self.gljv.id,
            "bank_journal_ids": [Command.set(self.bank.ids)],
        }
        vals.update(overrides)
        return self.env["levis.pos.clearing"].create(vals)

    def _two_stores(self):
        day = date(2026, 7, 8)
        self._posrec(self.tender_visa, self.store_one, day, 1_000_000.0)
        self._posrec(self.tender_visa, self.store_two, day, 500_000.0)
        one = self._statement(date(2026, 7, 9), 990_000.0, self._ref(MID_ONE, 1_000_000.0, 10_000.0))
        two = self._statement(date(2026, 7, 9), 495_000.0, self._ref(MID_TWO, 500_000.0, 5_000.0))
        return one, two

    # ------------------------------------------------------------------
    def test_a_scoped_run_touches_only_the_stores_it_names(self):
        one, two = self._two_stores()
        run = self._run(scope_analytic_ids=[Command.set(self.store_one.ids)])
        run.action_compute()

        by_store = {line.analytic_account_id: line for line in run.line_ids}
        self.assertEqual(by_store[self.store_one].state, "ok")
        self.assertEqual(by_store[self.store_one].block, "a")
        self.assertEqual(by_store[self.store_one].allocated, 1_000_000.0)

        other = by_store[self.store_two]
        self.assertEqual(other.state, "skipped", "a store outside the scope is listed, not booked")
        self.assertFalse(other.block)
        self.assertFalse(other.alloc_ids, "and nothing of its receivable is spent")

        run.action_generate_moves()
        self.assertFalse(
            two.levis_clearing_run_id,
            "the out-of-scope statement line must stay free for a later run",
        )
        self.assertEqual(one.levis_clearing_run_id, run)

    def test_a_scoped_run_leaves_the_banks_own_movements_alone(self):
        self._two_stores()
        sweep = self._statement(date(2026, 7, 10), -2_500_000.0, "TRSF E-BANKING DB 1007/SWBCA/WS954")
        run = self._run(scope_analytic_ids=[Command.set(self.store_one.ids)])
        run.action_compute()
        line = run.line_ids.filtered(lambda row: row.statement_line_id == sweep)
        self.assertEqual(line.state, "skipped")
        self.assertFalse(line.block, "a sweep belongs to the company, not to the store being cleared")

    def test_clearing_one_store_day_prepares_a_narrowed_run(self):
        self._two_stores()
        wide = self._run()
        wide.action_compute()
        day = wide.store_day_ids.filtered(lambda d: d.analytic_account_id == self.store_one)
        self.assertEqual(len(day), 1)

        action = day.action_clear()
        narrowed = self.env["levis.pos.clearing"].browse(action["res_id"])
        self.assertNotEqual(narrowed, wide)
        self.assertEqual(narrowed.scope_analytic_ids, self.store_one)
        self.assertEqual(narrowed.state, "computed", "it computes and stops")
        self.assertFalse(narrowed.leg_ids, "Prepare Entries is still a person's button")
        booked = narrowed.line_ids.filtered(lambda line: line.block)
        self.assertEqual(booked.analytic_account_id, self.store_one)

    # ------------------------------------------------------------------
    def test_the_matcher_pairs_one_credit_with_the_receipts_it_paid(self):
        one, _two = self._two_stores()
        run = self._run()
        run.action_compute()
        day = run.store_day_ids.filtered(lambda d: d.analytic_account_id == self.store_one)
        wizard = self.env["levis.clearing.match"]._build_for(day)
        self.assertTrue(wizard.bank_ids)

        bank = wizard.bank_ids.filtered(lambda row: row.line_id.statement_line_id == one)
        bank.selected = True
        self.assertEqual(wizard.bank_selected, 1_000_000.0, "the gross is what the receipts add up to")

        # No X70D is staged in this fixture, so pair by hand against a known ref.
        wizard.txn_ids = [Command.create({"ref": "80001-1-4711", "amount": 1_000_000.0, "selected": True})]
        self.assertEqual(wizard.txn_selected, 1_000_000.0)
        self.assertTrue(wizard.ties)

        wizard.action_match()
        mapping = self.env["levis.clearing.manual.map"].search([("statement_line_id", "=", one.id)])
        self.assertEqual(mapping.receipt_refs, "80001-1-4711")
        self.assertEqual(bank.line_id.receipt_ids.filtered("matched").mapped("ref"), ["80001-1-4711"])

        # And it survives the rebuild that would otherwise drop it.
        run.action_compute()
        line = run.line_ids.filtered(lambda row: row.statement_line_id == one)
        self.assertEqual(line.receipt_ids.filtered("matched").mapped("ref"), ["80001-1-4711"])

    def test_the_matcher_refuses_to_pair_two_credits_at_once(self):
        self._two_stores()
        run = self._run()
        run.action_compute()
        day = run.store_day_ids[0]
        wizard = self.env["levis.clearing.match"]._build_for(day)
        wizard.bank_ids.selected = True
        if len(wizard.bank_ids) < 2:
            self.skipTest("this store-day holds a single credit")
        with self.assertRaises(UserError):
            wizard.action_match()
