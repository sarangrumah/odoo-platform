# -*- coding: utf-8 -*-
"""Retail import profile — declares how to parse one source file type.

Generalizes ``custom.bank.import.template`` (column-index parsing) to:
- both ``.xlsx`` (openpyxl) and ``.csv`` sources,
- a configurable ``data_start_row`` (X70T/X31/X32P have a title row before the
  real header; X101 data starts on row 3; the Store Master header is on row 3),
- a generic logical-field -> 1-based-column map stored as JSON, so a new retail
  tenant just edits profile records instead of writing code.

The profile turns raw file bytes into a list of dicts keyed by logical field
name. The per-file-type loading into Odoo models lives in
``retail.import.executor``.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Source encoding lost U+00AE (R-in-circle) -> restore it. Same fix as the
# era_busana X101 extractor.
_ENCODING_REPL = {"�": "®"}

# Spreadsheet error sentinels. openpyxl is opened with data_only=True, so a
# cached =VLOOKUP/=MATCH error cell yields the literal string (e.g. "#N/A")
# instead of a value. Left unscrubbed these leak into category names, product
# names, SKUs and barcodes (a real product.category literally named "#N/A" was
# observed). Treat them as empty so downstream blank-handling / validation kicks
# in. Matched case-insensitively against the whole stripped cell.
_ERROR_SENTINELS = frozenset(
    {
        "#N/A",
        "N/A",
        "#REF!",
        "#VALUE!",
        "#DIV/0!",
        "#NAME?",
        "#NUM!",
        "#NULL!",
        "NULL",
    }
)

# Logical field names whose cells are IDENTIFIERS or LABELS, never arithmetic.
# Excel types a whole column numerically as soon as one cell looks like a number
# -- an ITEM SIZE column gets that treatment the moment Levi's ships a half size
# (10.5) -- and openpyxl then hands back int/float. Those cells end up as dict
# keys, external-ID seeds, ``default_code``, ``barcode`` and
# ``product.attribute.value`` names, so they must first become their exact text.
# Amount/date fields are deliberately absent: they keep their native
# int/float/datetime and go through _parse_amount / _parse_date.
# An unlisted field keeps the old behaviour, so the list fails safe.
TEXT_FIELDS = frozenset(
    {
        # X101 material master
        "product_code",
        "description",
        "brand",
        "category",
        "class",
        "klass",
        "subclass",
        "sku",
        "size",
        "inseam",
        "gtin",
        # store / transaction identity
        "store_code",
        "sap_store_code",
        "store_name",
        "register",
        "transnum",
        "document_id",
        "doc_id",
        # item identity
        "item_id",
        "item_code",
        "item_description",
        "item_type",
        "line_id",
        "ean",
        "waist",
        # free text / party identity
        "staff_id",
        "staff_name",
        "member_id",
        "member_type",
        "customer_phone",
        "omni_order_id",
        "line_comment",
        "transaction_note",
        # tender + discount labels
        "tender_type",
        "auth",
        "voucher",
        "discount_code",
        # CoA and the company key/value sheet
        "code",
        "account_name",
        "account_type",
        "field",
        "value",
    }
)
# Slot-numbered X24 discount columns. The amount/percentage slots are money and
# are deliberately excluded.
_TEXT_FIELD_PREFIXES = ("discount_type_", "discount_code_", "discount_description_")


def _is_text_field(name: str) -> bool:
    return name in TEXT_FIELDS or name.startswith(_TEXT_FIELD_PREFIXES)


def _number_to_text(value: Any) -> Any:
    """Exact text of a numerically-typed cell; every other type passes through.

    ITEM SIZE 10 arrives from openpyxl as ``10.0`` and EAN 4550703351542 as
    ``4550703351542.0``. Those must become ``"10"`` and ``"4550703351542"`` --
    never ``"10.0"``, never ``"4.550703351542e+12"``. A half size (``10.5``)
    keeps its fraction: that is a real Levi's size, not a float artefact.
    """
    if value is None or isinstance(value, str):
        return value  # the caller's existing handling applies
    if isinstance(value, bool):
        return value  # bool is an int; leave it to str() as today
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return ""  # NaN/inf is not an identifier
        if value.is_integer():
            # int() is exact below 2**53, which covers every 13/14-digit GTIN.
            return str(int(value))
        return format(Decimal(str(value)), "f")  # 10.5 -> "10.5"; 1e-05 -> "0.00001"
    if isinstance(value, Decimal):
        return str(int(value)) if value == value.to_integral_value() else format(value, "f")
    return value  # datetime/date/anything else


FILE_TYPES = [
    ("x101", "X101 — Material Master (products)"),
    ("x20", "X20 — Current On-hand Inventory"),
    ("x24", "X24DN — Retail Sales Detail (POS)"),
    ("x70d", "X70D — Tender Detail (payments)"),
    ("x70t", "X70T — Tender Settlement"),
    ("x31", "X31 — Discount Journal (promotions)"),
    ("x32p", "X32P — Stock Movement with Price (reference)"),
    ("x70", "X70 — Tender Breakdown"),
    ("x26", "X26 — Shipping"),
    ("x29", "X29 — Inventory Adjustment"),
    ("x48", "X48 — Customer Return"),
    ("x53", "X53 — Return to Vendor (RTV)"),
    ("x53_ebr", "X53-EBR — Return to Vendor (alternate format)"),
    ("x21", "X21 — Payment Summary"),
    ("x25n", "X25N — Receiving"),
    ("coa", "Chart of Accounts"),
    ("store_master", "Store Master / Warehouses"),
    ("company", "Company / Legal Entity"),
]


class RetailImportProfile(models.Model):
    _name = "retail.import.profile"
    _description = "Retail Import Profile"
    _order = "sequence, name"

    name = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(required=True, index=True, help="Stable identifier, e.g. 'levis_x101'.")
    file_type = fields.Selection(FILE_TYPES, required=True, index=True)
    company_id = fields.Many2one("res.company", string="Company", default=lambda s: s.env.company, required=True)
    active = fields.Boolean(default=True)
    namespace = fields.Char(
        default="retail_import",
        required=True,
        help="ir.model.data module namespace for external IDs (idempotency). Use a per-tenant value, e.g. 'levis'.",
    )

    # --- source format ---
    file_format = fields.Selection([("xlsx", "Excel (.xlsx)"), ("csv", "CSV")], default="xlsx", required=True)
    sheet_name = fields.Char(help="For xlsx: sheet to read. Empty = active/first sheet.")
    data_start_row = fields.Integer(
        default=2,
        required=True,
        help="1-based row where DATA begins (rows above are title/header and are skipped). "
        "X101=3, Store Master=3, X24/X70D=2.",
    )
    encoding = fields.Selection(
        [("utf-8", "UTF-8"), ("utf-8-sig", "UTF-8 (BOM)"), ("latin-1", "Latin-1")],
        default="utf-8-sig",
        required=True,
    )
    delimiter = fields.Char(default=",", size=1, help="CSV only.")

    # --- column mapping ---
    column_map_json = fields.Text(
        required=True,
        default="{}",
        help="JSON object mapping logical field name -> 1-based column index, e.g. "
        '{"product_code": 2, "description": 3, "sku": 10}. Indices are 1-based to '
        "match spreadsheet column letters (A=1).",
    )

    # --- parsing helpers config ---
    date_format = fields.Char(
        default="%Y-%m-%d",
        help="Python strptime format for string dates. Empty = accept datetime cells as-is.",
    )
    decimal_separator = fields.Char(default=".", size=1)
    thousand_separator = fields.Char(default=",", size=1)
    fix_encoding = fields.Boolean(default=True, help="Restore U+FFFD -> '®' on all string cells (X101 quirk).")

    sample_file = fields.Binary(string="Sample File", attachment=True)
    sample_filename = fields.Char()

    _code_uniq = models.Constraint(
        "unique(code, company_id)",
        "Profile code must be unique per company.",
    )

    # ------------------------------------------------------------------
    # Column map
    # ------------------------------------------------------------------
    def _column_map(self) -> dict[str, int]:
        self.ensure_one()
        try:
            raw = json.loads(self.column_map_json or "{}")
        except (ValueError, TypeError) as e:
            raise UserError(_("Profile %s has invalid column_map_json: %s") % (self.code, e)) from e
        out: dict[str, int] = {}
        for k, v in raw.items():
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                raise UserError(_("Profile %s column_map: index for %r must be an integer, got %r") % (self.code, k, v))
        return out

    # ------------------------------------------------------------------
    # Cell coercion
    # ------------------------------------------------------------------
    def _clean_str(self, raw: Any) -> str:
        if raw is None:
            return ""
        s = str(raw)
        if self.fix_encoding:
            for k, v in _ENCODING_REPL.items():
                s = s.replace(k, v)
        s = s.strip()
        if s.upper() in _ERROR_SENTINELS:
            return ""
        return s

    def _clean_cell(self, raw: Any) -> str:
        """``_clean_str`` for identifier/label cells: numbers first become their exact text."""
        return self._clean_str(_number_to_text(raw))

    def _parse_amount(self, raw: Any) -> Decimal:
        if raw is None or raw == "":
            return Decimal("0")
        if isinstance(raw, (int, float, Decimal)):
            return Decimal(str(raw))
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
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw
        s = str(raw).strip()
        if not s:
            return False
        if self.date_format:
            try:
                return datetime.strptime(s, self.date_format).date()
            except ValueError:
                pass
        # tolerant fallbacks
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return False

    @staticmethod
    def _safe_cell(row, idx_1based: int):
        if not idx_1based or idx_1based <= 0:
            return None
        i = idx_1based - 1
        if 0 <= i < len(row):
            return row[i]
        return None

    # ------------------------------------------------------------------
    # Readers
    # ------------------------------------------------------------------
    def _read_rows_xlsx(self, file_bytes: bytes):
        """Yield raw row tuples (data_start_row onward), streaming to bound memory."""
        try:
            import openpyxl  # noqa: PLC0415 - optional, image-provided
        except ImportError as e:  # pragma: no cover - depends on image
            raise UserError(
                _("openpyxl is not installed in this Odoo image. Add it to odoo/requirements.txt and rebuild.")
            ) from e
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        try:
            ws = wb[self.sheet_name] if self.sheet_name else wb.active
            start = max(self.data_start_row, 1)
            for row in ws.iter_rows(min_row=start, values_only=True):
                yield row
        finally:
            wb.close()

    def _read_rows_csv(self, file_bytes: bytes):
        text = file_bytes.decode(self.encoding or "utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text), delimiter=self.delimiter or ",")
        start = max(self.data_start_row, 1)
        for n, row in enumerate(reader, start=1):
            if n < start:
                continue
            yield row

    def _iter_raw_rows(self, file_bytes: bytes):
        if self.file_format == "csv":
            yield from self._read_rows_csv(file_bytes)
        else:
            yield from self._read_rows_xlsx(file_bytes)

    # ------------------------------------------------------------------
    # Public parse API
    # ------------------------------------------------------------------
    def read_records(self, file_b64: str, limit: int | None = None):
        """Parse a base64 file into a list of dicts keyed by logical field name.

        Blank rows are skipped. Returns ``{"records": [...], "total_rows": N,
        "blank_rows": M}``. String values are cleaned; callers coerce numbers/dates
        per-field via ``_parse_amount`` / ``_parse_date`` as needed.
        """
        self.ensure_one()
        col_map = self._column_map()
        file_bytes = base64.b64decode(file_b64)
        records: list[dict] = []
        total = 0
        blank = 0
        for raw in self._iter_raw_rows(file_bytes):
            total += 1
            row = list(raw)
            if not row or all((c is None or str(c).strip() == "") for c in row):
                blank += 1
                continue
            rec = {}
            for field_name, idx in col_map.items():
                cell = self._safe_cell(row, idx)
                if _is_text_field(field_name):
                    # An identifier/label column: a numerically-typed cell must not
                    # reach the executor as 10.0 / 4550703351542.0 -- those become
                    # default_code, barcode and attribute-value names verbatim.
                    rec[field_name] = self._clean_cell(cell)
                else:
                    rec[field_name] = self._clean_str(cell) if isinstance(cell, str) else cell
            rec["_row"] = total + self.data_start_row - 1
            records.append(rec)
            if limit and len(records) >= limit:
                break
        return {"records": records, "total_rows": total, "blank_rows": blank}
