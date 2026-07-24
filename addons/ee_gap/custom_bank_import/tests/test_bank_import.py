# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
from decimal import Decimal

from odoo.tests import TransactionCase, tagged

from odoo.addons.custom_adapter_framework.models.adapter_base import (
    AdapterResponse,
    BaseAdapter,
)
from odoo.addons.custom_adapter_framework.models.adapter_registry import (
    register_adapter,
)


@register_adapter("bank_test_mock_h2h")
class _MockH2HAdapter(BaseAdapter):
    fixture_lines: list[dict] = []

    def inquiry_balance(self, account_number):
        return AdapterResponse(ok=True, status_code=200, data={"balance": 1000.0})

    def inquiry_statement(self, account_number, date_from, date_to):
        return AdapterResponse(
            ok=True,
            status_code=200,
            data={"lines": list(self.fixture_lines)},
        )


@tagged("post_install", "-at_install")
class TestBankImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Template = cls.env["custom.bank.import.template"]
        cls.Wizard = cls.env["custom.bank.import.csv.wizard"]
        cls.Log = cls.env["custom.bank.import.log"]
        cls.Conn = cls.env["custom.bank.h2h.connection"]
        cls.AdapterConfig = cls.env["custom.adapter.config"]

        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Test Bank",
                "type": "bank",
                "code": "TBNK",
            }
        )
        cls.template = cls.Template.create(
            {
                "name": "Test CSV",
                "code": "test_csv",
                "encoding": "utf-8",
                "delimiter": ",",
                "has_header": True,
                "date_format": "%Y-%m-%d",
                "date_column_index": 1,
                "ref_column_index": 2,
                "signed_amount_column_index": 3,
                "decimal_separator": ".",
                "thousand_separator": "",
            }
        )

    # ----- CSV happy path -----

    def test_csv_happy_path(self):
        csv = b"date,ref,amount\n2026-05-01,REF001,1500.00\n2026-05-02,REF002,-250.00\n2026-05-03,REF003,75.50\n"
        wiz = self.Wizard.create(
            {
                "journal_id": self.journal.id,
                "template_id": self.template.id,
                "file": base64.b64encode(csv).decode(),
                "filename": "happy.csv",
            }
        )
        action = wiz.action_import()
        self.assertEqual(action["res_model"], "custom.bank.import.log")
        log = self.Log.browse(action["res_id"])
        self.assertEqual(log.state, "imported")
        self.assertEqual(log.line_count, 3)
        self.assertEqual(log.error_count, 0)
        statement = log.statement_id
        self.assertTrue(statement)
        self.assertEqual(len(statement.line_ids), 3)
        amounts = sorted(statement.line_ids.mapped("amount"))
        self.assertEqual(amounts, [-250.0, 75.5, 1500.0])

    # ----- CSV bad date format -----

    def test_csv_bad_date_format_graceful(self):
        csv = (
            b"date,ref,amount\n"
            b"NOT-A-DATE,REF001,1500.00\n"
            b"2026/13/40,REF002,200.00\n"  # bad day
            b"2026-05-03,REF003,75.50\n"  # one good row
        )
        wiz = self.Wizard.create(
            {
                "journal_id": self.journal.id,
                "template_id": self.template.id,
                "file": base64.b64encode(csv).decode(),
                "filename": "bad-dates.csv",
            }
        )
        action = wiz.action_import()
        log = self.Log.browse(action["res_id"])
        self.assertEqual(log.state, "partial")
        self.assertEqual(log.line_count, 1)
        self.assertGreaterEqual(log.error_count, 2)
        self.assertIn("Bad/missing date", log.raw_payload or "")

    # ----- BCA corporate (KlikBCA Bisnis / CorpAcctTrxn) auto-detect -----

    def test_bca_corp_autodetect(self):
        # Real-world layout: preamble + DD/MM dates (no year) + fused Jumlah+CR/DB
        # column + Saldo Awal/Mutasi/Saldo Akhir footer. Any template routes to the
        # BCA-corp handler once the signature is detected.
        csv = (
            b'"Informasi Rekening - Mutasi Rekening"," "," "," "," ",\n'
            b"\n"
            b'"No. rekening : 2685151268"\n'
            b'"Nama : ERA BUSANA RETAILINDO PT"\n'
            b'"Periode : 01/06/2026 - 30/06/2026"\n'
            b'"Kode Mata Uang : Rp"\n'
            b'"Tanggal Transaksi","Keterangan","Cabang","Jumlah","Saldo"\n'
            b'"01/06","BIAYA ADM       ","0000","30,000.00 DB","2,313,178.27"\n'
            b'"13/06","KR OTOMATIS MID : 885004608391 LEVIS PIM 2   ","0000","10,930,941.82 CR","13,244,120.09"\n'
            b'"Saldo Awal : 2,343,178.27"\n'
            b'"Mutasi Debet : 30,000.00","1"\n'
            b'"Mutasi Kredit : 10,930,941.82","1"\n'
            b'"Saldo Akhir : 13,244,120.09"\n'
        )
        res = self.template.parse_csv(base64.b64encode(csv).decode())
        self.assertEqual(res["errors"], [])
        self.assertEqual(len(res["lines"]), 2)
        by_amount = sorted(res["lines"], key=lambda ln: ln["amount"])
        debit, credit = by_amount[0], by_amount[1]
        # DB -> negative (money out), CR -> positive (money in)
        self.assertEqual(debit["amount"], Decimal("-30000.00"))
        self.assertEqual(credit["amount"], Decimal("10930941.82"))
        # DD/MM resolved against the period year, whitespace-collapsed description
        self.assertEqual(debit["date"].year, 2026)
        self.assertEqual(debit["date"].month, 6)
        self.assertEqual(debit["date"].day, 1)
        self.assertEqual(debit["ref"], "BIAYA ADM")
        self.assertIn("LEVIS PIM 2", credit["ref"])

    def test_bca_corp_full_date_variant(self):
        # Second real-world variant: "Tanggal Transaksi" carries the full
        # DD/MM/YYYY date instead of year-less DD/MM.
        csv = (
            b'"Informasi Rekening - Mutasi Rekening"," "," "," "," ",\n'
            b'"Periode : 01/07/2026 - 20/07/2026"\n'
            b'"Tanggal Transaksi","Keterangan","Cabang","Jumlah","Saldo"\n'
            b'"01/07/2026","KR OTOMATIS MID : 885004608387 LEVIS SENAYAN CITY  ","0998","4,689,356.40 CR","7,273,422.02"\n'
            b'"20/07/2026","TRSF E-BANKING DB","0000","960,064,168.95 DB","2,500,000.00"\n'
            b'"Saldo Akhir : 2,500,000.00"\n'
        )
        res = self.template.parse_csv(base64.b64encode(csv).decode())
        self.assertEqual(res["errors"], [])
        self.assertEqual(len(res["lines"]), 2)
        credit, debit = res["lines"]
        self.assertEqual(credit["amount"], Decimal("4689356.40"))
        self.assertEqual(credit["date"], debit["date"].replace(day=1))
        self.assertEqual(debit["date"].isoformat(), "2026-07-20")
        self.assertEqual(debit["amount"], Decimal("-960064168.95"))

    def test_bca_corp_via_wizard_imports(self):
        csv = (
            b'"Informasi Rekening - Mutasi Rekening"," "," "," "," ",\n'
            b'"Periode : 01/06/2026 - 30/06/2026"\n'
            b'"Tanggal Transaksi","Keterangan","Cabang","Jumlah","Saldo"\n'
            b'"01/06","BIAYA ADM","0000","30,000.00 DB","2,313,178.27"\n'
            b'"13/06","SETORAN","0000","1,000,000.00 CR","3,313,178.27"\n'
            b'"Saldo Akhir : 3,313,178.27"\n'
        )
        wiz = self.Wizard.create(
            {
                "journal_id": self.journal.id,
                "template_id": self.template.id,
                "file": base64.b64encode(csv).decode(),
                "filename": "bca-corp.csv",
            }
        )
        action = wiz.action_import()
        log = self.Log.browse(action["res_id"])
        self.assertEqual(log.state, "imported")
        self.assertEqual(log.line_count, 2)
        self.assertEqual(log.error_count, 0)
        amounts = sorted(log.statement_id.line_ids.mapped("amount"))
        self.assertEqual(amounts, [-30000.0, 1000000.0])

    # ----- H2H mock adapter -----

    def test_h2h_mock_adapter_creates_lines(self):
        _MockH2HAdapter.fixture_lines = [
            {"date": "2026-05-01", "description": "Salary", "ref": "SAL001", "amount": 5000.0},
            {"date": "2026-05-02", "description": "Vendor pay", "ref": "VND001", "amount": -1200.0},
        ]
        cfg = self.AdapterConfig.create(
            {
                "name": "test-h2h",
                "adapter_type": "bank_test_mock_h2h",
                "base_url": "http://localhost/none",
                "auth_method": "none",
                "timeout_s": 1,
                "retry_count": 1,
                "circuit_breaker_threshold": 5,
                "circuit_breaker_cooldown_s": 60,
            }
        )
        conn = self.Conn.create(
            {
                "name": "Mock Conn",
                "bank_code": "Other",
                "adapter_config_id": cfg.id,
                "account_number": "1234567890",
                "journal_id": self.journal.id,
                "sync_interval_minutes": 1,
            }
        )
        conn._do_sync()
        log = self.Log.search(
            [("journal_id", "=", self.journal.id), ("filename", "like", "h2h-Other-%")], limit=1, order="id desc"
        )
        self.assertTrue(log)
        self.assertEqual(log.line_count, 2)
        self.assertTrue(log.statement_id)
        self.assertEqual(len(log.statement_id.line_ids), 2)
        self.assertEqual(conn.status, "active")
        self.assertTrue(conn.last_sync_at)
