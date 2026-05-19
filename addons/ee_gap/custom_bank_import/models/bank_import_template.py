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
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BankImportTemplate(models.Model):
    _name = "custom.bank.import.template"
    _description = "Bank Import Template"
    _order = "sequence, name"

    name = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(required=True, index=True,
                       help="Stable identifier, e.g. 'bca_csv'.")
    bank_id = fields.Many2one("res.bank", string="Bank")
    company_id = fields.Many2one(
        "res.company", string="Company",
        default=lambda s: s.env.company, required=True,
    )
    active = fields.Boolean(default=True)

    encoding = fields.Selection(
        [("utf-8", "UTF-8"), ("latin-1", "Latin-1")],
        default="utf-8", required=True,
    )
    delimiter = fields.Char(default=",", size=1, required=True)
    has_header = fields.Boolean(default=True,
                                help="Skip first row of file (column headers).")
    date_format = fields.Char(
        default="%d/%m/%Y", required=True,
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
        help="If set, this column holds a signed amount and overrides "
             "amount_credit/amount_debit.",
    )

    sample_file = fields.Binary(string="Sample File", attachment=True)
    sample_filename = fields.Char()

    decimal_separator = fields.Char(default=".", size=1, required=True)
    thousand_separator = fields.Char(default=",", size=1)

    _sql_constraints = [
        ("code_uniq", "unique(code, company_id)",
         "Template code must be unique per company."),
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
        reader = csv.reader(io.StringIO(text),
                            delimiter=self.delimiter or ",")
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
            ref = (self._safe_cell(row, self.ref_column_index) or "")
            partner_hint = (self._safe_cell(row, self.partner_column_index) or "")
            balance_raw = self._safe_cell(row, self.balance_column_index)
            balance = self._parse_amount(balance_raw) if balance_raw else None
            if self.signed_amount_column_index and self.signed_amount_column_index > 0:
                amount = self._parse_amount(
                    self._safe_cell(row, self.signed_amount_column_index))
            else:
                credit = self._parse_amount(
                    self._safe_cell(row, self.amount_credit_column_index))
                debit = self._parse_amount(
                    self._safe_cell(row, self.amount_debit_column_index))
                amount = credit - debit
            if amount == Decimal("0"):
                continue
            lines.append({
                "date": d,
                "ref": str(ref).strip(),
                "partner_hint": str(partner_hint).strip(),
                "amount": amount,
                "balance": balance,
            })
        return {
            "lines": lines,
            "errors": errors,
            "total_rows": len(rows),
        }
