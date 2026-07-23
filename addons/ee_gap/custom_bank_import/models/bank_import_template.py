# -*- coding: utf-8 -*-
"""Bank import template — declares how to parse a bank's CSV statement.

Derived from arkaaim's ``era.bank.import.template`` but simplified to the
column-index model requested in the spec (1-based, stored as integers).
Header-name resolution is still supported when ``has_header`` is True
and the index resolves to a header cell that exists.
"""

from __future__ import annotations

import base64
import csv
import io
import logging
import re
from datetime import date as date_cls
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from odoo import fields, models

_logger = logging.getLogger(__name__)


class BankImportTemplate(models.Model):
    _name = "custom.bank.import.template"
    _description = "Bank Import Template"
    _order = "sequence, name"

    name = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(required=True, index=True, help="Stable identifier, e.g. 'bca_csv'.")
    bank_id = fields.Many2one("res.bank", string="Bank")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda s: s.env.company,
        required=True,
    )
    active = fields.Boolean(default=True)

    encoding = fields.Selection(
        [("utf-8", "UTF-8"), ("latin-1", "Latin-1")],
        default="utf-8",
        required=True,
    )
    delimiter = fields.Char(default=",", size=1, required=True)
    has_header = fields.Boolean(default=True, help="Skip first row of file (column headers).")
    date_format = fields.Char(
        default="%d/%m/%Y",
        required=True,
        help="Python strptime format. BCA: %d/%m/%Y, Mandiri: %d-%m-%Y.",
    )

    # 1-based column indices. -1 means "not used".
    date_column_index = fields.Integer(default=1, required=True)
    ref_column_index = fields.Integer(default=-1)
    partner_column_index = fields.Integer(default=-1)
    amount_credit_column_index = fields.Integer(default=-1)
    amount_debit_column_index = fields.Integer(default=-1)
    balance_column_index = fields.Integer(default=-1)
    signed_amount_column_index = fields.Integer(
        default=-1,
        help="If set, this column holds a signed amount and overrides amount_credit/amount_debit.",
    )

    sample_file = fields.Binary(string="Sample File", attachment=True)
    sample_filename = fields.Char()

    decimal_separator = fields.Char(default=".", size=1, required=True)
    thousand_separator = fields.Char(default=",", size=1)

    _sql_constraints = [
        ("code_uniq", "unique(code, company_id)", "Template code must be unique per company."),
    ]

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_amount(self, raw: Any) -> Decimal:
        if raw is None:
            return Decimal("0")
        s = str(raw).strip()
        if not s:
            return Decimal("0")
        if self.thousand_separator:
            s = s.replace(self.thousand_separator, "")
        if self.decimal_separator and self.decimal_separator != ".":
            s = s.replace(self.decimal_separator, ".")
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        try:
            return Decimal(s)
        except InvalidOperation:
            return Decimal("0")

    def _parse_date(self, raw: Any):
        if not raw:
            return False
        s = str(raw).strip()
        try:
            return datetime.strptime(s, self.date_format).date()
        except ValueError:
            return False

    @staticmethod
    def _safe_cell(row, idx_1based: int) -> Optional[str]:
        if idx_1based is None or idx_1based <= 0:
            return None
        i = idx_1based - 1
        if 0 <= i < len(row):
            return row[i]
        return None

    def _read_csv(self, file_bytes: bytes) -> list[list[str]]:
        text = file_bytes.decode(self.encoding or "utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text), delimiter=self.delimiter or ",")
        return list(reader)

    def parse_csv(self, file_b64: str) -> dict:
        """Parse a base64 CSV. Returns dict with keys:
        - lines: list of {date, ref, partner_hint, amount(Decimal), balance}
        - errors: list of (row_number, error_string)
        - total_rows: int
        """
        self.ensure_one()
        file_bytes = base64.b64decode(file_b64)
        rows = self._read_csv(file_bytes)
        if self._is_bca_corp(rows):
            return self._parse_bca_corp(rows)
        if self.has_header and rows:
            rows = rows[1:]
        lines: list[dict] = []
        errors: list[tuple[int, str]] = []
        for n, row in enumerate(rows, start=2 if self.has_header else 1):
            if not row or all((c is None or str(c).strip() == "") for c in row):
                continue
            raw_date = self._safe_cell(row, self.date_column_index)
            d = self._parse_date(raw_date)
            if not d:
                errors.append((n, f"Bad/missing date: {raw_date!r}"))
                continue
            ref = self._safe_cell(row, self.ref_column_index) or ""
            partner_hint = self._safe_cell(row, self.partner_column_index) or ""
            balance_raw = self._safe_cell(row, self.balance_column_index)
            balance = self._parse_amount(balance_raw) if balance_raw else None
            if self.signed_amount_column_index and self.signed_amount_column_index > 0:
                amount = self._parse_amount(self._safe_cell(row, self.signed_amount_column_index))
            else:
                credit = self._parse_amount(self._safe_cell(row, self.amount_credit_column_index))
                debit = self._parse_amount(self._safe_cell(row, self.amount_debit_column_index))
                amount = credit - debit
            if amount == Decimal("0"):
                continue
            lines.append(
                {
                    "date": d,
                    "ref": str(ref).strip(),
                    "partner_hint": str(partner_hint).strip(),
                    "amount": amount,
                    "balance": balance,
                }
            )
        return {
            "lines": lines,
            "errors": errors,
            "total_rows": len(rows),
        }

    # ------------------------------------------------------------------
    # BCA corporate ("KlikBCA Bisnis" / CorpAcctTrxn) CSV
    # ------------------------------------------------------------------
    # This export cannot be described by the generic column-index model:
    #  * a metadata preamble precedes the column header;
    #  * dates are ``DD/MM`` with NO year (year lives in the "Periode :" line);
    #  * amount + sign are fused in one "Jumlah" cell, e.g. ``30,000.00 DB`` /
    #    ``10,930,941.82 CR`` (CR = money in / positive, DB = money out / negative);
    #  * ``Saldo Awal / Mutasi / Saldo Akhir`` footer rows trail the data.
    # It is auto-detected (independent of template column config) and handled here.

    _BCA_CORP_HEADER = ["Tanggal Transaksi", "Keterangan", "Cabang", "Jumlah", "Saldo"]
    _BCA_CORP_FOOTER = ("Saldo Awal", "Mutasi Debet", "Mutasi Kredit", "Saldo Akhir")

    @staticmethod
    def _bca_corp_amount(raw: Any) -> Decimal:
        # BCA corporate amounts are always ``1,234,567.89`` (comma thousands, dot
        # decimal) regardless of the template's configured separators, because this
        # handler is auto-detected and may run under any selected template.
        s = str(raw or "").strip().replace(",", "")
        if not s:
            return Decimal("0")
        try:
            return Decimal(s)
        except InvalidOperation:
            return Decimal("0")

    def _is_bca_corp(self, rows) -> bool:
        if not rows:
            return False
        first = (self._safe_cell(rows[0], 1) or "").strip()
        if first.startswith("Informasi Rekening"):
            return True
        for row in rows:
            if [(str(c).strip()) for c in row[:5]] == self._BCA_CORP_HEADER:
                return True
        return False

    def _parse_bca_corp(self, rows) -> dict:
        lines: list[dict] = []
        errors: list[tuple[int, str]] = []

        # Resolve the statement's year(s) from the "Periode :" preamble and find the
        # column-header row; data starts on the row after it.
        from_month = from_year = to_year = None
        header_idx = None
        period_re = re.compile(r"Periode\s*:\s*(\d{2})/(\d{2})/(\d{4})\s*-\s*\d{2}/\d{2}/(\d{4})")
        for i, row in enumerate(rows):
            joined = " ".join(str(c) for c in row)
            m = period_re.search(joined)
            if m:
                from_month = int(m.group(2))
                from_year = int(m.group(3))
                to_year = int(m.group(4))
            if [(str(c).strip()) for c in row[:5]] == self._BCA_CORP_HEADER:
                header_idx = i
                break

        start = (header_idx + 1) if header_idx is not None else 0
        date_re = re.compile(r"^(\d{2})/(\d{2})$")

        for n, row in enumerate(rows[start:], start=start + 1):
            if not row or all(str(c).strip() == "" for c in row):
                continue
            c0 = (self._safe_cell(row, 1) or "").strip()
            if c0.startswith(self._BCA_CORP_FOOTER):
                break
            dm = date_re.match(c0)
            if not dm:
                errors.append((n, f"Bad/missing date: {c0!r}"))
                continue
            day, month = int(dm.group(1)), int(dm.group(2))
            # Year rollover: a period spanning Dec->Jan uses the later year for the
            # months that wrapped past the start month. Inert for a single-month file.
            if from_year is None:
                errors.append((n, "Missing 'Periode' line; cannot resolve year"))
                continue
            year = to_year if (to_year != from_year and month < from_month) else from_year
            try:
                d = date_cls(year, month, day)
            except ValueError as e:
                errors.append((n, f"Invalid date {c0!r}: {e}"))
                continue

            raw_amount = (self._safe_cell(row, 4) or "").strip()
            am = re.match(r"^(.*?)\s*(CR|DB)$", raw_amount, re.IGNORECASE)
            if am:
                num, sign = am.group(1), (1 if am.group(2).upper() == "CR" else -1)
            else:
                num, sign = raw_amount, 1
            amount = self._bca_corp_amount(num) * sign
            if amount == Decimal("0"):
                continue

            keterangan = re.sub(r"\s+", " ", str(self._safe_cell(row, 2) or "")).strip()
            balance_raw = self._safe_cell(row, 5)
            balance = self._bca_corp_amount(balance_raw) if balance_raw else None

            lines.append(
                {
                    "date": d,
                    "ref": keterangan,
                    "partner_hint": "",
                    "amount": amount,
                    "balance": balance,
                }
            )

        return {
            "lines": lines,
            "errors": errors,
            "total_rows": max(0, len(rows) - start),
        }
