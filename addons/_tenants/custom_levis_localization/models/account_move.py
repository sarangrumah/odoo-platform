# -*- coding: utf-8 -*-
"""Journal Billing printout helpers on ``account.move``.

The Journal Billing document renders a posted vendor bill as a GL voucher:
a two-column meta header (Reference / Invoice AP / dates / amount-in-words on
the left; Vendor / PO / Tax on the right) and a GL table of every journal item
(GL account, description, operating unit, debit, credit).

All lookups that depend on optional modules (l10n_id tax number, analytic
"operating unit", linked PO) are resolved defensively here so the QWeb stays
declarative and never crashes on a DB where a field is absent.
"""

from __future__ import annotations

from odoo import models

from .terbilang import terbilang_id


class AccountMove(models.Model):
    _inherit = "account.move"

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _edo_first_field(self, *names, default=""):
        """Return the first populated value among ``names`` that actually
        exists on this model — tolerant of optional l10n modules."""
        self.ensure_one()
        for name in names:
            if name in self._fields and self[name]:
                return self[name]
        return default

    def _edo_gl_lines(self):
        """Journal items shown in the GL table (excludes section/note rows)."""
        self.ensure_one()
        return self.line_ids.filtered(
            lambda l: l.display_type not in ("line_section", "line_note")
        )

    # ------------------------------------------------------------------
    # Header meta
    # ------------------------------------------------------------------
    def _edo_po_number(self):
        """PO reference: linked purchase order(s), else the bill origin."""
        self.ensure_one()
        if "purchase_line_id" in self.line_ids._fields:
            names = self.line_ids.mapped("purchase_line_id.order_id.name")
            names = sorted({n for n in names if n})
            if names:
                return ", ".join(names)
        return self.invoice_origin or ""

    def _edo_tax_number(self):
        """Faktur Pajak / tax invoice number.

        Levi's carries this in ``x_custom_nsfp`` (No. Faktur Pajak / NSFP, from
        ``custom_coretax``); the l10n_id names are kept as fallbacks so the
        report still works on a DB without Coretax.
        """
        return self._edo_first_field(
            "x_custom_nsfp", "l10n_id_tax_number", "l10n_id_kode_transaksi", default=""
        )

    def _edo_tax_date(self):
        """Tax point date — Coretax "Tanggal Faktur Pajak" (``x_custom_tanggal_
        faktur_pajak``), then any l10n_id tax date, finally the invoice date."""
        self.ensure_one()
        return self._edo_first_field(
            "x_custom_tanggal_faktur_pajak", "l10n_id_tax_date", default=False
        ) or self.invoice_date

    def _edo_exchange_rate(self):
        """Rate of the bill currency against the company currency (1.0 when equal)."""
        self.ensure_one()
        if self.currency_id == self.company_id.currency_id:
            return 1.0
        if self.amount_total:
            return abs(self.amount_total_signed) / self.amount_total
        return 1.0

    def _edo_bill_warehouse(self):
        """Warehouse(s)/store(s) of the purchase order(s) behind this bill."""
        self.ensure_one()
        if "purchase_line_id" not in self.line_ids._fields:
            return self.env["stock.warehouse"]
        orders = self.line_ids.mapped("purchase_line_id.order_id")
        return orders.mapped("picking_type_id.warehouse_id")

    def _edo_operating_unit(self, line):
        """"Operating Unit" = the warehouse/store from the source document.

        Uses the warehouse of the PO behind this specific line; lines without a
        PO link (tax, payable) fall back to the bill's warehouse, and finally to
        the company name when the bill has no purchase origin at all.
        """
        self.ensure_one()
        pol = line.purchase_line_id if "purchase_line_id" in line._fields else False
        wh = pol.order_id.picking_type_id.warehouse_id if pol else False
        if not wh:
            wh = self._edo_bill_warehouse()[:1]
        if wh:
            return wh.name
        return self.company_id.name or ""

    # ------------------------------------------------------------------
    # Amount in words
    # ------------------------------------------------------------------
    def _edo_amount_in_words(self):
        self.ensure_one()
        suffix = "Rupiah" if self.currency_id.name == "IDR" else (self.currency_id.currency_unit_label or "")
        return terbilang_id(self.amount_total, suffix=suffix)
