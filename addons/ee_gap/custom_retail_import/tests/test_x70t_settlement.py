# -*- coding: utf-8 -*-
"""X70T: the nightly file that names the acquirer, and settles what X70D drops.

Levi's POS began issuing acquirer-level tenders on 16-Sep-2026 -- BCA_QRIS,
BCA_DEBIT_GPN, BRI_REGULAR_OFF_US and ten more. The nightly X70D does not carry
those rows at all: over 87 nightly pairs the two files agree to the rupiah on
every day that used only the OFFLINE_*/CASH vocabulary, and X70D is short by
exactly the acquirer-coded tenders on the days that did not. X24DN still bills
the whole sale, so the difference (Rp 389.478.201 over 16-24 Sep 2026) sits on
POS Suspense Clearing with nothing to clear it.

Two shapes have to survive parsing, and both are load-bearing:

* X70T is a **cross-tab** -- one column per tender, and the set of columns
  changes every night, because only the tenders a store actually took get one.
  An index-based column map cannot follow that;
* the report ends each row with its own ``NON CASH(Total)`` subtotal, which
  staged as a tender would double the day's card settlement.

And one arithmetic property: the settlement posts the **difference** between
what X70T reports and what the day has already settled, so X70D-then-X70T,
X70T-then-X70D, and the same file twice all book each tender exactly once.
"""

from __future__ import annotations

import base64
import io

from odoo.tests.common import TransactionCase, tagged

#: The X70T header, verbatim from the 24-Sep-2026 file (column 2 really is blank).
#: Kept here so a layout change shows up as a failing assertion rather than as a
#: column-map edit nobody can date.
_HEADER = (
    "STORE CODE",
    "",
    "SAP STORE CODE",
    "STORE NAME",
    "TRANS DATE",
    "TERMINAL",
    "CASH",
    "BCA_CARD",
    "BCA_QRIS",
    "OFFLINE_DOMESTIC_CARD",
    "NON CASH(Total)",
)

#: Real store-days from 23/24-Sep-2026. 80431 is one of the stores whose card
#: tenders X70D reports nothing of; 80438 opened and took nothing.
_ROWS = (
    ("80431", "", "0020080431", "OLS SES - AEON BSD", "2026-09-24", 1, 2250800, 3151700, 11156900, None, 14308600),
    ("80129", "", "0020080129", "OLS SES - TUNJUNGAN", "2026-09-24", 1, 1901800, None, None, 34114500, 34114500),
    ("80438", "", "0020080438", "OLS SES - GRAND CITY", "2026-09-24", 1, None, None, None, None, None),
    ("80431", "", "0020080431", "OLS SES - AEON BSD", "2026-09-23", 1, None, None, 1000000, None, 1000000),
)


def _workbook() -> str:
    """The report as base64: nine metadata rows, header on row 10, data from 11."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "X70T_Tender_Settlement_Report"
    ws.append(("X70T_Tender_Settlement_Report",))
    for _ in range(8):
        ws.append(("",))
    ws.append(_HEADER)
    for row in _ROWS:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


@tagged("post_install", "-at_install", "levis", "retail_import")
class TestX70tSettlement(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile = cls.env.ref("custom_retail_import.profile_levis_x70t")
        cls.executor = cls.env["retail.import.executor"]
        cls.company = cls.profile.company_id
        cls.env["ir.config_parameter"].sudo().set_param("retail_import.x24_decouple_payment", "1")
        cls.env["ir.config_parameter"].sudo().set_param("retail_import.x70t_post_enabled", "1")

    def _log(self, name="X70T_Tender_Settlement_Report__20260924T193011Z.xlsx"):
        return self.env["retail.import.log"].create({"profile_id": self.profile.id, "filename": name})

    def _rirec_lines(self):
        journal = self.executor._ri_rirec_journal(self.company)
        return self.env["account.move.line"].search([("journal_id", "=", journal.id)])

    # -- parsing ------------------------------------------------------------
    def test_01_every_tender_column_becomes_its_own_row(self):
        out = self.profile.read_wide_records(
            _workbook(), "tender_type", "tender_amount", ignore_captions=self.executor._X70T_TOTAL_CAPTIONS
        )
        pairs = {(r["store_code"], r["trans_date"], r["tender_type"]): r["tender_amount"] for r in out["records"]}
        self.assertEqual(pairs[("80431", "2026-09-24", "BCA_QRIS")], "11156900")
        self.assertEqual(pairs[("80431", "2026-09-24", "CASH")], "2250800")
        self.assertEqual(pairs[("80129", "2026-09-24", "OFFLINE_DOMESTIC_CARD")], "34114500")
        self.assertEqual(len(out["records"]), 6, "one record per non-empty tender cell")

    def test_02_the_reports_own_subtotal_is_never_a_tender(self):
        out = self.profile.read_wide_records(
            _workbook(), "tender_type", "tender_amount", ignore_captions=self.executor._X70T_TOTAL_CAPTIONS
        )
        self.assertNotIn(
            "NON CASH(Total)",
            {r["tender_type"] for r in out["records"]},
            "the subtotal column was staged as a tender; every card day would double",
        )

    def test_03_a_store_that_took_nothing_is_not_a_row_of_zeroes(self):
        out = self.profile.read_wide_records(
            _workbook(), "tender_type", "tender_amount", ignore_captions=self.executor._X70T_TOTAL_CAPTIONS
        )
        self.assertFalse([r for r in out["records"] if r["store_code"] == "80438"])
        # Counted, never silently lost: 4 source rows = 3 that expanded + 1 empty.
        self.assertEqual(out["total_rows"], 4)
        self.assertEqual(out["blank_rows"], 1)

    # -- settlement ---------------------------------------------------------
    def test_04_one_transfer_per_trading_day(self):
        self.executor._post_x70t_settlement(self.profile, _workbook(), self._log())
        moves = self._rirec_lines().mapped("move_id")
        self.assertEqual(len(moves), 2, "one entry per trading day, not one per store")
        self.assertEqual({str(m.date) for m in moves}, {"2026-09-24", "2026-09-23"})
        for move in moves:
            self.assertEqual(move.state, "posted")
            self.assertAlmostEqual(sum(move.line_ids.mapped("debit")), sum(move.line_ids.mapped("credit")), 2)
        day = moves.filtered(lambda m: str(m.date) == "2026-09-24")
        by_tender = {
            ln.account_id.name: ln.debit for ln in day.line_ids if ln.debit and ln.account_id.name.startswith("POS Re")
        }
        self.assertEqual(by_tender["POS Receivable - BCA_QRIS"], 11156900)
        self.assertEqual(by_tender["POS Receivable - CASH"], 1901800 + 2250800)
        self.assertEqual(by_tender["POS Receivable - OFFLINE_DOMESTIC_CARD"], 34114500)

    def test_05_running_it_twice_settles_each_tender_once(self):
        self.executor._post_x70t_settlement(self.profile, _workbook(), self._log())
        first = sum(self._rirec_lines().mapped("debit"))
        second_log = self._log("X70T_Tender_Settlement_Report__20260925T193011Z.xlsx")
        self.executor._post_x70t_settlement(self.profile, _workbook(), second_log)
        self.assertEqual(sum(self._rirec_lines().mapped("debit")), first, "the day was settled a second time")
        self.assertEqual(second_log.records_created, 0)

    def test_06_only_the_part_a_day_still_owes_is_posted(self):
        """X70D settled part of 24-Sep already; X70T tops the rest up, not the whole."""
        susp = self.executor._x24_suspense_account(self.company)
        recv = self.executor._x24_recv_account_for(self.company, "BCA_QRIS")
        self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.executor._ri_rirec_journal(self.company).id,
                "date": "2026-09-24",
                "company_id": self.company.id,
                "ref": "already settled by hand",
                "line_ids": [
                    (
                        0,
                        0,
                        {"account_id": recv.id, "debit": 5000000, "credit": 0.0, "name": "X70D settlement BCA_QRIS"},
                    ),
                    (0, 0, {"account_id": susp.id, "debit": 0.0, "credit": 5000000, "name": "X70D settlement"}),
                ],
            }
        ).action_post()

        self.executor._post_x70t_settlement(self.profile, _workbook(), self._log())
        qris = {
            str(ln.date): ln.debit
            for ln in self._rirec_lines()
            if ln.account_id == recv and ln.debit and ln.move_id.ref and "X70T" in ln.move_id.ref
        }
        self.assertEqual(qris["2026-09-24"], 11156900 - 5000000, "the hand-posted part was booked twice")
        # The untouched day is unaffected: netting is per day and tender, not per file.
        self.assertEqual(qris["2026-09-23"], 1000000)

    def test_07_staged_and_silent_while_the_switch_is_off(self):
        self.env["ir.config_parameter"].sudo().set_param("retail_import.x70t_post_enabled", "0")
        log = self._log()
        self.executor._load_x70t(self.profile, _workbook(), log)
        self.assertFalse(self._rirec_lines(), "a gated loader posted to the ledger")
        lines = self.env["retail.import.line"].search([("log_id", "=", log.id)])
        # Staging reads the sheet as it stands -- one line per store-day row, the empty
        # store included. Only the settlement path unpivots into tender cells.
        self.assertEqual(len(lines), len(_ROWS))
        self.assertEqual(set(lines.mapped("state")), {"skipped"})
