# -*- coding: utf-8 -*-
"""Tests for the numeric-cell to text coercion in the reader and the X101 seam.

Excel types a whole column numerically as soon as one of its cells looks like a
number. Levi's footwear ships half sizes, so the moment ``10.5`` appears in ITEM
SIZE the entire column turns numeric and openpyxl hands back ``10.0`` and ``10.5``
instead of ``"10"`` and ``"10.5"``. The X101 loader then did
``(r.get("size") or "").strip()`` and the whole import died with
``'float' object has no attribute 'strip'``.

The crash was the loud half. The quiet half is worse: a numerically-typed GTIN
column would have written ``4550703351542.0`` into ``product.product.barcode``, and
a size of ``10.0`` would have created a second ``product.attribute.value`` next to
the ``10`` already in the database.

So these tests pin three things: the coercion rule itself, that it is applied to
identifier columns *and only* to them (amounts and dates must keep their native
types for ``_parse_amount``/``_parse_date``), and that a numeric workbook now
imports to exactly the same database state as its text equivalent.
"""

from __future__ import annotations

import base64
import io
from datetime import datetime
from decimal import Decimal

from odoo.tests.common import TransactionCase, tagged

from ..models.retail_import_profile import _is_text_field, _number_to_text
from .test_x101_seam import _COLUMNS, _as_records

#: The reported case: one whole-number size and its half-size sibling on the same
#: template, with every identifier column typed numerically the way Excel does it.
_NUMERIC_ROWS = [
    (
        "ZT77A-0001",
        "SNEAKER LOW",
        "LEVIS",
        "MENS FOOTWEAR",
        "SHOES",
        "SNEAKER",
        "ZT77A0001010",
        10,  # int cell
        "-",
        4550703351535,  # int GTIN
        749900,
        "2026-01-01 00:00:00",
    ),
    (
        "ZT77A-0001",
        "SNEAKER LOW",
        "LEVIS",
        "MENS FOOTWEAR",
        "SHOES",
        "SNEAKER",
        "ZT77A000101 0.5",  # placeholder, rewritten below
        10.5,  # float cell -- the half size
        "-",
        4550703351542,
        749900,
        "2026-01-01 00:00:00",
    ),
]
# The PROD SKU is composed as PRODUCT_CODE without dashes + "0" + SIZE + INSEAM.
_NUMERIC_ROWS[1] = _NUMERIC_ROWS[1][:6] + ("ZT77A0001010.5",) + _NUMERIC_ROWS[1][7:]

#: The same two rows with every cell already text -- the golden reference.
_TEXT_ROWS = [
    row[:7] + (str(row[7]) if row[7] != 10.0 else "10",) + (row[8], str(row[9])) + row[10:]
    for row in _NUMERIC_ROWS
]


def _build_xlsx(rows, price_eff=None):
    """An X101-shaped workbook that preserves each cell's Python type.

    ``test_x101_seam._build_xlsx`` does the same, but this variant can also put a
    real ``datetime`` in PRICE EFFECTIVE FROM, which is what the reader must be
    shown to leave alone.
    """
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["X101 Material Master"])
    ws.append([])
    for row in rows:
        cells = [None] * max(_COLUMNS)
        for value, column in zip(row, _COLUMNS):
            cells[column - 1] = value
        if price_eff is not None:
            cells[_COLUMNS[-1] - 1] = price_eff
        ws.append(cells)
    buffer = io.BytesIO()
    wb.save(buffer)
    return base64.b64encode(buffer.getvalue())


@tagged("post_install", "-at_install")
class TestNumberToText(TransactionCase):
    """The coercion rule, in isolation."""

    def test_integral_values_lose_the_fraction(self):
        self.assertEqual(_number_to_text(10), "10")
        self.assertEqual(_number_to_text(10.0), "10")
        self.assertEqual(_number_to_text(-0.0), "0")
        self.assertEqual(_number_to_text(Decimal("10.00")), "10")

    def test_half_size_keeps_its_fraction(self):
        """10.5 is a real Levi's size, not a float artefact."""
        self.assertEqual(_number_to_text(10.5), "10.5")
        self.assertEqual(_number_to_text("10.5"), "10.5")

    def test_large_ean_never_uses_scientific_notation(self):
        for value in (4550703351542.0, 45507033515421.0):
            with self.subTest(value=value):
                text = _number_to_text(value)
                self.assertNotIn("e", text.lower())
                self.assertNotIn(".", text)
                self.assertEqual(text, str(int(value)))

    def test_tiny_float_is_expanded(self):
        self.assertEqual(_number_to_text(1e-05), "0.00001")

    def test_non_numeric_types_pass_through(self):
        stamp = datetime(2026, 1, 1)
        self.assertIsNone(_number_to_text(None))
        self.assertEqual(_number_to_text("  34  "), "  34  ")  # stripping is _clean_str's job
        self.assertIs(_number_to_text(True), True)
        self.assertIs(_number_to_text(stamp), stamp)

    def test_nan_and_infinity_are_not_identifiers(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                self.assertEqual(_number_to_text(value), "")


@tagged("post_install", "-at_install")
class TestTextFieldAllowlist(TransactionCase):
    """Which columns get coerced. Over-coercing is as much a bug as under-coercing."""

    def test_identifier_columns_are_text(self):
        for name in (
            "product_code",
            "sku",
            "size",
            "inseam",
            "gtin",
            "ean",
            "waist",
            "store_code",
            "transnum",
            "discount_code_1",
            "discount_type_3",
        ):
            with self.subTest(name=name):
                self.assertTrue(_is_text_field(name))

    def test_money_and_date_columns_are_not(self):
        """These must reach _parse_amount / _parse_date as int/float/datetime."""
        for name in (
            "retail_price",
            "price_eff",
            "trans_date",
            "net_amount",
            "qty",
            "onhand_qty",
            "discount_amount_1",
            "discount_percentage_1",
        ):
            with self.subTest(name=name):
                self.assertFalse(_is_text_field(name))


@tagged("post_install", "-at_install")
class TestProfileReaderCoercion(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile = cls.env.ref("custom_retail_import.profile_levis_x101")

    def test_clean_cell_reuses_clean_str(self):
        self.assertEqual(self.profile._clean_cell("#N/A"), "")
        self.assertEqual(self.profile._clean_cell("  X  "), "X")
        self.assertEqual(self.profile._clean_cell(None), "")
        self.assertEqual(self.profile._clean_cell(10.0), "10")

    def test_reader_coerces_only_the_text_columns(self):
        stamp = datetime(2026, 1, 1)
        records = self.profile.read_records(_build_xlsx(_NUMERIC_ROWS, price_eff=stamp))["records"]
        self.assertEqual(len(records), 2)

        self.assertEqual(records[0]["size"], "10")
        self.assertEqual(records[1]["size"], "10.5")
        self.assertEqual(records[0]["gtin"], "4550703351535")
        self.assertEqual(records[1]["sku"], "ZT77A0001010.5")

        # The regression guard: amounts and dates keep their native types.
        self.assertNotIsInstance(records[0]["retail_price"], str)
        self.assertIsInstance(records[0]["price_eff"], datetime)


@tagged("post_install", "-at_install")
class TestX101NumericCells(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Executor = cls.env["retail.import.executor"]
        cls.profile = cls.env.ref("custom_retail_import.profile_levis_x101")
        cls.namespace = cls.profile.namespace

    def _make_log(self):
        return self.env["retail.import.log"].create(
            {"profile_id": self.profile.id, "filename": "numeric.xlsx"}
        )

    def _variant(self, sku):
        return self.env["product.product"].search([("default_code", "=", sku)])

    def test_numeric_size_column_imports_without_failing(self):
        """The reported failure: this raised 'float' object has no attribute 'strip'."""
        log = self._make_log()
        self.Executor._load_x101(self.profile, _build_xlsx(_NUMERIC_ROWS), log)
        self.assertNotEqual(log.state, "failed", log.error_message)
        self.assertFalse(log.error_message)
        self.assertEqual(len(self._variant("ZT77A0001010")), 1)
        self.assertEqual(len(self._variant("ZT77A0001010.5")), 1)

    def test_half_size_does_not_duplicate_the_attribute_value(self):
        """Size 10 and 10.5 are two values -- and "10.0" must never be a third."""
        self.Executor._load_x101(self.profile, _build_xlsx(_NUMERIC_ROWS), self._make_log())
        product = self._variant("ZT77A0001010")
        size_attr = product.product_template_variant_value_ids.attribute_id
        self.assertEqual(len(size_attr), 1)
        names = self.env["product.attribute.value"].search([("attribute_id", "=", size_attr.id)]).mapped("name")
        self.assertIn("10", names)
        self.assertIn("10.5", names)
        self.assertNotIn("10.0", names)
        self.assertEqual(names.count("10"), 1)

    def test_numeric_gtin_is_written_as_digits(self):
        self.Executor._load_x101(self.profile, _build_xlsx(_NUMERIC_ROWS), self._make_log())
        for sku, gtin in (("ZT77A0001010", "4550703351535"), ("ZT77A0001010.5", "4550703351542")):
            with self.subTest(sku=sku):
                product = self._variant(sku)
                self.assertEqual(product.barcode, gtin)
                resolvable = {product.barcode} | set(product.barcode_ids.mapped("barcode"))
                self.assertFalse([code for code in resolvable if "." in code])
                self.assertEqual(self.env["product.product"]._resolve_barcode(gtin), product)

    def test_numeric_identifiers_do_not_leak_into_the_external_id(self):
        """A float product_code would seed the xid as TMPL_12345_0."""
        rows = [
            (12345, "NUMERIC CODE", "LEVIS", "MENS TOPS", "TEES", "SHORT SLEEVE", 678900, "M", "-", "", 199900, "")
        ]
        self.Executor._x101_upsert_items(_as_records(rows), self.namespace)
        tmpl_id = self.Executor._xid_get(
            self.namespace, self.Executor._safe_xid("tmpl_", "12345"), "product.template"
        )
        self.assertTrue(tmpl_id, "the template xid must be seeded from the integer text")
        self.assertEqual(len(self._variant("678900")), 1)

    def test_numeric_and_text_cells_produce_identical_state(self):
        """The golden parity test: numeric cells must land exactly where text does.

        Both runs happen in one transaction, so the text run is given a parallel set
        of codes -- otherwise it would just re-find the first run's records.
        """

        def _state(rows):
            out = {}
            for row in rows:
                product = self._variant(row[6])
                self.assertTrue(product, f"{row[6]} was not created")
                out[row[6]] = {
                    "barcode": product.barcode,
                    "values": sorted(product.product_template_variant_value_ids.mapped("name")),
                    "categ": product.categ_id.complete_name,
                    "price": product.product_tmpl_id.list_price,
                }
            return out

        self.Executor._load_x101(self.profile, _build_xlsx(_NUMERIC_ROWS), self._make_log())
        from_numeric = _state(_NUMERIC_ROWS)

        shifted = []
        for row in _TEXT_ROWS:
            row = list(row)
            row[0] = row[0].replace("ZT77A", "ZT78A")
            row[6] = row[6].replace("ZT77A", "ZT78A")
            row[9] = "9" + row[9][1:]
            shifted.append(tuple(row))
        self.Executor._x101_upsert_items(_as_records(shifted), self.namespace)
        from_text = _state(shifted)

        for numeric_row, text_row in zip(_NUMERIC_ROWS, shifted):
            numeric = dict(from_numeric[numeric_row[6]])
            text = dict(from_text[text_row[6]])
            self.assertEqual(numeric.pop("values"), text.pop("values"))
            self.assertEqual(numeric.pop("categ"), text.pop("categ"))
            self.assertEqual(numeric.pop("price"), text.pop("price"))
            # The barcodes were shifted apart on purpose; only their shape is comparable.
            self.assertEqual(len(numeric["barcode"]), len(text["barcode"]))
            self.assertNotIn(".", text["barcode"])


@tagged("post_install", "-at_install")
class TestStagedRowNormalisation(TransactionCase):
    """Rows staged before the coercion existed still carry JSON floats."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Executor = cls.env["retail.import.executor"]

    def test_legacy_row_normalises_to_the_same_keys(self):
        row = self.Executor._ri_normalize_row(
            {"register": 1.0, "transnum": 1234.0, "ean": 4550703351542.0, "tender_amount": 5000.5}
        )
        self.assertEqual(row["register"], "1")
        self.assertEqual(row["transnum"], "1234")
        self.assertEqual(row["ean"], "4550703351542")
        self.assertEqual(row["tender_amount"], 5000.5, "an amount must stay a number")
