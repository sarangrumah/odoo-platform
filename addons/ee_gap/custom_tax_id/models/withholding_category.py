# -*- coding: utf-8 -*-
"""Catalogue of withholding-tax 'jenis penghasilan' under Indonesian PPh.

Separating the catalogue from rates lets us version the tarif independently
(e.g. when DJP issues a PMK that changes the rate for jasa konsultan only)
without losing the historical mapping on already-posted bukti potong.
"""

from __future__ import annotations

from odoo import api, fields, models


class WithholdingCategory(models.Model):
    _name = "tax.withholding.category"
    _description = "PPh Withholding Category (jenis penghasilan)"
    _order = "pph_kind, code"

    # The picker on the vendor bill is labelled "Kode Objek PPh", so typing the
    # code has to find the record. Searching ``name`` alone forces the operator
    # to type a 60-character "jenis penghasilan" sentence to reach one of 108
    # rows. ``bupot_object_code`` (24-104-01) is what the tax team quotes;
    # ``code`` (Z5-AF) is our internal handle -- both are accepted.
    _rec_names_search = ["bupot_object_code", "code", "name"]

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True, help="Short identifier, e.g. JASA, SEWA, ROYALTI")
    pph_kind = fields.Selection(
        [
            ("pph_23", "PPh 23"),
            ("pph_4_2", "PPh 4(2) Final"),
            ("pph_26", "PPh 26 (Penghasilan ke LN)"),
            ("pph_22", "PPh 22"),
            ("pph_21", "PPh 21 (Personal — payroll module)"),
        ],
        required=True,
    )
    legal_basis = fields.Char(help="e.g. Pasal 23 UU PPh, PMK 141/2015")
    bupot_object_code = fields.Char(
        help="Kode objek pajak as referenced by Coretax e-Bupot XML. See PER-04/PJ/2023 attachment."
    )
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        "unique(code)",
        "Withholding category code must be unique.",
    )

    @api.depends("bupot_object_code", "name")
    def _compute_display_name(self):
        """Lead with the kode objek pajak so the operator can confirm the pick
        without opening the record -- "24-104-01 - Jasa Teknik"."""
        for category in self:
            code = category.bupot_object_code or category.code
            category.display_name = "%s - %s" % (code, category.name) if code else (category.name or "")
