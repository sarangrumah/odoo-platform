# -*- coding: utf-8 -*-
"""Telling one sender from another, and one workbook from another.

Two kinds of mail arrive at the same address and mean different things. The
X-Store application mails raw output from the till system, every night, named by
a machine. A shop mails its own recap of the same trading days -- the supporting
document for the tender, carrying columns the raw feed does not have -- named by
whoever happened to send it.

The day the store mailbox was switched on, 19 shops sent 25 attachments in one
afternoon. Twenty were genuine X70D exports. The filename glob staged ten. The
others had arrived as "Report Sales OLS SES Grand Metropolitan Mall Periode
September", "LAPORAN X70D BULAN SEPTEMBER", "3. X70D_Tender_Detail_Report OLS
PIM 2". So the decision moved to what the workbook contains.

Two further facts from that afternoon are pinned here because both cost a round
to discover:

* the same workbook heads column 11 ``Payment Method`` on one tab and ``PAYMENT``
  on another, so a signature may only test the columns that never move;
* the shops put their store code in the subject ("LAPORAN SALES 80432 18092026")
  right next to a date that looks exactly like one.
"""

from __future__ import annotations

import base64
import io

from odoo.tests.common import TransactionCase, tagged

_X70D_HEADER = (
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
#: The same report, as the first tab of the real Kelapa Gading workbook heads it.
_X70D_HEADER_ALT = _X70D_HEADER[:10] + ("Payment Method", "APP CODE")
#: What a "LAPORAN HARIAN" actually is: a retype, and not this report.
_DAILY_HEADER = (
    "No.",
    "Tanggal Invoice",
    "No Tiket",
    "APP CODE",
    "Payment Method",
    "Tanggal Settlement / Transfer",
    "Invoice Amount",
    "Keterangan",
)


def _wb(sheets) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, header, rows in sheets:
        ws = wb.create_sheet(title=title)
        ws.append(header)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(store="80433", txn=5372, amount=2649700, payment="BCA - QRIS"):
    return (
        int(store),
        "00200" + store,
        "OLS SES - SOMEWHERE",
        "2026-09-17",
        1,
        txn,
        "80433001000002",
        "Someone",
        "OFFLINE_OTHER_CREDITCARD",
        amount,
        payment,
        "113512",
    )


@tagged("post_install", "-at_install", "levis", "retail_import")
class TestStoreMailRouting(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.box = cls.env.ref("custom_retail_import.mailbox_levis_store_tender")
        cls.profile = cls.env.ref("custom_retail_import.profile_levis_x70d_store")

    # -- who sent it ----------------------------------------------------
    def test_01_sender_kinds(self):
        for addr, kind in (
            ('"X-Center" <XcenterAdmin@levi.com>', "auto"),
            ("xcenteradmin@levi.com", "auto"),
            ("Levi's Plaza Senayan <levis.ps@erajaya.com>", "store"),
            ("levis.theparkkendari@erajaya.com", "store"),
            ("Rizky <rizky.rinaldi@erajaya.com>", "person"),
            ("", "person"),
        ):
            self.assertEqual(self.box._sender_kind(addr), kind, addr)

    def test_02_levi_com_is_never_mistaken_for_a_store(self):
        """'levi.com' contains 'levi'; the store prefix is 'levis.' and local-part only."""
        self.assertEqual(self.box._sender_kind("levis.data@levi.com"), "auto")

    # -- which store ----------------------------------------------------
    def test_03_store_code_from_subject(self):
        for subject, code in (
            ("LAPORAN SALES 80432 18092026", "80432"),
            ("Laporan sales (0020080747) (18/9/2026)", "80747"),
            ("REPORT SALES 20080741 2026-09-18", "80741"),
            ("LAPORAN SALES (80446) (18092026)", "80446"),
            ("REPORT X70D 18 SEPTEMBER 2026 OLS CENTRAL PARK", False),
            ("X31_Discount_Journal was executed at 8/20/2026 3:30:09 AM", False),
            ("LAPORAN SALES 80432 dan 80433", False),
        ):
            self.assertEqual(self.box._subject_store_code(subject), code, subject)

    # -- which workbook -------------------------------------------------
    def test_04_named_anything_staged_on_content(self):
        raw = _wb([("2026-09-17", _X70D_HEADER, [_row()])])
        for filename in (
            "X70D_Tender_Detail_Report.xlsx",
            "Report Sales OLS SES Grand Metropolitan Mall Periode September.xlsx",
            "LAPORAN X70D BULAN SEPTEMBER.xlsx",
            "3. X70D_Tender_Detail_Report OLS PIM 2 SEPTEMBER 2026.xlsx",
        ):
            ingest, why, _codes = self.box._should_ingest(filename, raw, False)
            self.assertTrue(ingest, f"{filename} -> {why}")

    def test_05_a_retype_is_not_staged_however_it_is_named(self):
        raw = _wb([("SEP (1)", _DAILY_HEADER, [(1, "2026-09-01", 4678, "0", "CASH", "", 749900, "")])])
        ingest, why, _codes = self.box._should_ingest("X70D_LAPORAN_HARIAN.xlsx", raw, False)
        self.assertFalse(ingest)
        self.assertIn("TRANSNUM", why)

    def test_06_signature_tests_only_columns_that_never_move(self):
        """One workbook, two spellings of column 11. Both tabs must be accepted."""
        raw = _wb(
            [
                ("2026-09-01", _X70D_HEADER_ALT, [_row(txn=4671)]),
                ("2026-09-17", _X70D_HEADER, [_row(txn=5372)]),
            ]
        )
        sheets, codes = self.box._probe_xlsx(raw)
        self.assertEqual(sheets, 2)
        self.assertEqual(codes, {"80433"})
        out = self.profile.read_records(base64.b64encode(raw).decode())
        self.assertEqual(len(out["records"]), 2, "a tab was skipped over its caption")

    def test_07_non_matching_tabs_are_skipped_not_parsed(self):
        raw = _wb(
            [
                ("2026-09-17", _X70D_HEADER, [_row()]),
                ("PAYMENT", ("Payment Method",), [("CASH",), ("BCA - QRIS",)]),
            ]
        )
        out = self.profile.read_records(base64.b64encode(raw).decode())
        self.assertEqual(len(out["records"]), 1)
        self.assertEqual({r["store_code"] for r in out["records"]}, {"80433"})

    # -- the cross-check ------------------------------------------------
    def test_08_subject_and_file_must_agree(self):
        raw = _wb([("2026-09-17", _X70D_HEADER, [_row(store="80433")])])
        ingest, why, codes = self.box._should_ingest("whatever.xlsx", raw, "80447")
        self.assertFalse(ingest, "another outlet's export was staged")
        self.assertIn("80447", why)
        self.assertIn("80433", why)
        self.assertEqual(codes, {"80433"})

    def test_09_agreement_stages_it(self):
        raw = _wb([("2026-09-17", _X70D_HEADER, [_row(store="80433")])])
        ingest, _why, codes = self.box._should_ingest("whatever.xlsx", raw, "80433")
        self.assertTrue(ingest)
        self.assertEqual(codes, {"80433"})

    def test_10_no_subject_code_is_not_a_mismatch(self):
        """Most subjects do name a store. A silent one must not block the file."""
        raw = _wb([("2026-09-17", _X70D_HEADER, [_row()])])
        ingest, _why, _codes = self.box._should_ingest("whatever.xlsx", raw, False)
        self.assertTrue(ingest)

    def test_10b_a_numeric_store_code_cell_is_read_as_its_digits(self):
        """Excel types the column numerically: 80744.0, whose last five are "744.0"."""
        raw = _wb(
            [
                (
                    "2026-09-17",
                    _X70D_HEADER,
                    [
                        (80744.0,) + _row()[1:],
                    ],
                )
            ]
        )
        _sheets, codes = self.box._probe_xlsx(raw)
        self.assertEqual(codes, {"80744"})
        ingest, _why, _c = self.box._should_ingest("x.xlsx", raw, "80744")
        self.assertTrue(ingest, "a numeric cell made the file disagree with its own subject")

    def test_11_a_non_workbook_attachment_is_refused_quietly(self):
        ingest, _why, codes = self.box._should_ingest("notes.xlsx", b"this is not a workbook", False)
        self.assertFalse(ingest)
        self.assertFalse(codes)

    def test_12_the_nightly_mailbox_still_decides_by_filename(self):
        """Its files are machine-named and 7 MB; opening each one would be waste."""
        nightly = self.env.ref("custom_retail_import.mailbox_levis_xcenter")
        self.assertFalse(nightly.ingest_signature)
        ingest, _why, _codes = nightly._should_ingest("X70D_Tender_Detail_Report.xlsx", b"", False)
        self.assertTrue(ingest)
        ingest, _why, _codes = nightly._should_ingest("X20_Current_Onhand.xlsx", b"", False)
        self.assertFalse(ingest)
