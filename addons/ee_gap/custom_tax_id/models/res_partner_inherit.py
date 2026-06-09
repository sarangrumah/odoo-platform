# -*- coding: utf-8 -*-
"""Partner tax attributes used by withholding resolution."""

from __future__ import annotations

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Indonesian NPWP is either 15 digits (legacy) or 16 digits (NIK-based since 2024).
NPWP_15_RE = re.compile(r"^\d{15}$")
NPWP_16_RE = re.compile(r"^\d{16}$")
NIK_RE = re.compile(r"^\d{16}$")


class ResPartner(models.Model):
    _inherit = "res.partner"

    x_custom_npwp = fields.Char(
        string="NPWP",
        help="Nomor Pokok Wajib Pajak. 15-digit legacy or 16-digit (NIK-based, post-2024).",
    )
    x_custom_nik = fields.Char(
        string="NIK (Custom)",
        help="Nomor Induk Kependudukan (16-digit). For individual partners (orang pribadi).",
    )
    x_custom_npwp_status = fields.Selection(
        [
            ("valid", "Valid NPWP"),
            ("invalid", "Invalid"),
            ("none", "Tidak ada NPWP"),
        ],
        compute="_compute_npwp_status",
        store=True,
    )
    x_custom_has_valid_npwp = fields.Boolean(
        compute="_compute_has_valid_npwp",
        store=True,
    )
    x_custom_pkp = fields.Boolean(
        string="PKP",
        help="Pengusaha Kena Pajak — registered for PPN. Affects fiscal position.",
    )
    x_custom_foreign_counterparty = fields.Boolean(
        string="Wajib Pajak Luar Negeri",
        compute="_compute_foreign_counterparty",
        store=True,
        help="Auto-set when the partner's country differs from the company country.",
    )

    @api.depends("x_custom_npwp")
    def _compute_npwp_status(self):
        for rec in self:
            v = (rec.x_custom_npwp or "").replace(".", "").replace("-", "")
            if not v:
                rec.x_custom_npwp_status = "none"
            elif NPWP_15_RE.match(v) or NPWP_16_RE.match(v):
                rec.x_custom_npwp_status = "valid"
            else:
                rec.x_custom_npwp_status = "invalid"

    @api.depends("x_custom_npwp_status")
    def _compute_has_valid_npwp(self):
        for rec in self:
            rec.x_custom_has_valid_npwp = rec.x_custom_npwp_status == "valid"

    @api.depends("country_id", "company_id", "country_id.code")
    def _compute_foreign_counterparty(self):
        for rec in self:
            company = rec.company_id or rec.env.company
            if not company.country_id or not rec.country_id:
                rec.x_custom_foreign_counterparty = False
            else:
                rec.x_custom_foreign_counterparty = rec.country_id != company.country_id

    @api.constrains("x_custom_nik")
    def _check_nik(self):
        for rec in self:
            if rec.x_custom_nik and not NIK_RE.match(rec.x_custom_nik):
                raise ValidationError(_("NIK harus 16 digit angka."))

    def check_vat_id(self, vat):
        """Relaxed Indonesian NPWP validation for the standard ``vat`` field.

        Core ``base_vat.check_vat_id`` requires a Luhn checksum on legacy
        15-digit NPWPs (and special-cases a leading ``0``), which rejects
        otherwise-valid numbers such as ``015556667008000``. Per business
        requirement we accept any 15- or 16-digit NPWP (legacy 15-digit or
        NIK-based 16-digit, post-2024), ignoring ``.``/``-``/space
        separators, and drop the checksum / leading-zero rules.
        """
        digits = re.sub(r"[ .\-]", "", vat or "")
        return bool(NPWP_15_RE.match(digits) or NPWP_16_RE.match(digits))
