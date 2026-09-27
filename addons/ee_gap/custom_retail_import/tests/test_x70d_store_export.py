# -*- coding: utf-8 -*-
"""The store-exported X70D: many worksheets, a TOTAL row, and the acquirer label.

The nightly corporate X70D and the X70D a store exports have the same twelve
columns in the same order, and disagree about the last two. The nightly report
heads them ``AUTH NUMBER`` / ``VOUCHER NUMBER`` and leaves them empty in every
row; the store export heads them ``PAYMENT`` / ``APPR CODE`` and fills them in.
``PAYMENT`` is the only place the acquirer and the card product appear together
("BCA - QRIS", "BRI - DEBIT OTHER"), and an MDR rate is keyed on exactly that:
``TENDER TYPE`` folds QRIS, debit and credit -- rates from 0% to 1.4% -- into one
bucket.

Two shape differences have to survive parsing, and both are load-bearing:

* the store export puts **one trading day per worksheet**, each with its own
  header row, so reading only the active sheet silently returns one day;
* every worksheet ends with a **TOTAL row** carrying an amount and no store code,
  which would otherwise be staged as a transaction and double a day's tender.
"""

from __future__ import annotations

import base64
import io

from odoo.tests.common import TransactionCase, tagged

#: Header of the store export, verbatim. Kept in the test so a future change to
#: the client's layout shows up here as a failing assertion rather than as a
#: column-map edit nobody can date.
_HEADER = (
    "STORE CODE",
    "SAP STORE CODE",
    "STORE NAME",
    "TRANS DATE",
    "REGISTER ",
    "TRANSNUM",
    "CASHIER LOGIN ID",
    "CASHIER NAME",
    "TENDER TYPE",
    "TENDER AMOUNT",
    "PAYMENT",
    "APPR CODE",
)

#: Two trading days from the real MKG September export, one sheet each, including
#: the mixed tender types that make PAYMENT necessary: the same
#: OFFLINE_OTHER_CREDITCARD bucket holds a 0% QRIS and a 0.15% on-us debit.
_DAYS = {
    "2026-09-17": [
        (
            80433,
            "0020080433",
            "OLS SES - KELAPA GADING MALL",
            "2026-09-17",
            1,
            5372,
            "80433001000002",
            "Iin Pituria",
            "OFFLINE_OTHER_CREDITCARD",
            2649700,
            "BCA - DEBIT BCA / BCA GPN",
            113512,
        ),
        (
            80433,
            "0020080433",
            "OLS SES - KELAPA GADING MALL",
            "2026-09-17",
            1,
            5379,
            "80433001000002",
            "Iin Pituria",
            "OFFLINE_OTHER_CREDITCARD",
            1550900,
            "BCA - QRIS",
            132059,
        ),
        (
            80433,
            "0020080433",
            "OLS SES - KELAPA GADING MALL",
            "2026-09-17",
            1,
            5406,
            "80433001000003",
            "Taufan Saputra",
            "OFFLINE_BRI_CREDIT_CARD",
            2399800,
            "BRI - DEBIT OTHER",
            805767,
        ),
    ],
    "2026-09-01": [
        (
            80433,
            "0020080433",
            "OLS SES - KELAPA GADING MALL",
            "2026-09-01",
            1,
            4678,
            "80433001000002",
            "Iin Pituria",
            "CASH",
            749900,
            "CASH",
            None,
        ),
    ],
}


def _workbook() -> str:
    """The store export as base64: one sheet per day, each ending in a TOTAL row."""
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for day, rows in _DAYS.items():
        ws = wb.create_sheet(title=day)
        ws.append(_HEADER)
        for row in rows:
            ws.append(row)
        total = sum(r[9] for r in rows)
        # Exactly how the client writes it: blank strings, the amount in its own
        # column, and no store code to identify it by.
        ws.append(("", "", "", "", "", "", "", "", "", total, "", ""))
    buf = io.BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


@tagged("post_install", "-at_install", "levis", "retail_import")
class TestX70dStoreExport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile = cls.env.ref("custom_retail_import.profile_levis_x70d_store")

    def test_01_every_worksheet_is_read(self):
        """One sheet per trading day: all of them, not just the active one."""
        out = self.profile.read_records(_workbook())
        days = {r["trans_date"] for r in out["records"]}
        self.assertEqual(days, set(_DAYS), "a trading day went missing: only one sheet was read")
        self.assertEqual(len(out["records"]), sum(len(v) for v in _DAYS.values()))

    def test_02_total_row_is_dropped(self):
        """The per-sheet TOTAL row carries an amount and no store code."""
        out = self.profile.read_records(_workbook())
        self.assertFalse(
            [r for r in out["records"] if not str(r.get("store_code") or "").strip()],
            "a TOTAL row was staged as a transaction; the day's tender would double",
        )
        # Dropped rows are counted, never silently lost: one TOTAL per sheet.
        self.assertEqual(out["blank_rows"], len(_DAYS))
        self.assertEqual(out["total_rows"], out["blank_rows"] + len(out["records"]))

    def test_03_payment_and_appr_code_are_named_for_what_they_hold(self):
        """Columns 11/12 must not inherit the nightly file's auth/voucher names."""
        out = self.profile.read_records(_workbook())
        by_txn = {str(r["transnum"]): r for r in out["records"]}
        self.assertEqual(by_txn["5379"]["payment"], "BCA - QRIS")
        self.assertEqual(by_txn["5379"]["appr_code"], "132059")
        self.assertNotIn("auth", by_txn["5379"])
        self.assertNotIn("voucher", by_txn["5379"])

    def test_04_one_tender_type_holds_several_acquirer_products(self):
        """Why PAYMENT is needed at all: TENDER TYPE cannot carry the MDR rate."""
        out = self.profile.read_records(_workbook())
        same_bucket = {r["payment"] for r in out["records"] if r["tender_type"] == "OFFLINE_OTHER_CREDITCARD"}
        self.assertEqual(same_bucket, {"BCA - QRIS", "BCA - DEBIT BCA / BCA GPN"})

    def test_05_rows_are_staged_and_never_posted(self):
        """The nightly file is the system of record; this one is a lookup."""
        name = "X70D_Tender_Detail_Report -OLS MKG SEPTEMBER 2026.xlsx"
        log = self.env["retail.import.log"].create({"profile_id": self.profile.id, "filename": name})
        # The loader is called directly, as the other suites do: ``run`` commits
        # around the handler and a commit cannot cross a TransactionCase.
        self.env["retail.import.executor"]._load_x70d_store(self.profile, _workbook(), log)

        lines = self.env["retail.import.line"].search([("log_id", "=", log.id)])
        self.assertEqual(len(lines), sum(len(v) for v in _DAYS.values()))
        self.assertEqual(set(lines.mapped("state")), {"skipped"})
        self.assertEqual(log.records_created, 0)
        self.assertFalse(
            lines.filtered("target_model"),
            "the store export must not create or link to any business record",
        )
