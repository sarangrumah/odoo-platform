# -*- coding: utf-8 -*-
"""account.tax extension for PPN DPP Nilai Lain (PMK 131/2024).

Background: Indonesian VAT (PPN) historically used the full invoice
subtotal as the Dasar Pengenaan Pajak. PMK 131/2024 codifies "DPP Nilai
Lain" — a reduced base — for specific categories (impor, film, emas
perhiasan, kendaraan bekas, paket wisata, agen perjalanan, jasa
pengiriman, hasil tembakau, jasa pemasaran perdagangan, jasa freight
forwarding, dll). Tax rate is unchanged but the base is multiplied by
``dpp_factor``, producing the correct effective burden.

Implementation: extend ``account.tax`` with three fields. When the tax
type uses ``dpp_method = nilai_lain``, we shadow ``amount`` calculations
via an overridden ``_compute_amount``.
"""

from __future__ import annotations

from odoo import _, api, fields, models


DPP_CATEGORY_SELECTION = [
    ("impor", "Impor BKP"),
    ("film", "Film Cerita"),
    ("emas_perhiasan", "Emas Perhiasan"),
    ("kendaraan_bekas", "Kendaraan Bekas"),
    ("paket_wisata", "Paket Wisata"),
    ("agen_perjalanan", "Agen Perjalanan"),
    ("jasa_pengiriman", "Jasa Pengiriman Paket"),
    ("hasil_tembakau", "Hasil Tembakau"),
    ("pemasaran_perdagangan", "Jasa Pemasaran Perdagangan"),
    ("freight_forwarding", "Jasa Freight Forwarding"),
    ("jasa_lain", "Jasa Lain (PMK 131/2024 lampiran)"),
    ("ppn_efektif_11_12", "PPN 11% efektif via DPP 11/12 (transisi 2025)"),
    ("ppn_efektif_12", "PPN 12% standar (per UU HPP roadmap)"),
]


class AccountTax(models.Model):
    _inherit = "account.tax"

    x_custom_dpp_method = fields.Selection(
        [
            ("regular", "DPP Regular (full subtotal)"),
            ("nilai_lain", "DPP Nilai Lain (PMK 131/2024)"),
        ],
        default="regular",
        string="DPP Method",
        help="Choose 'Nilai Lain' to use the reduced base per PMK 131/2024.",
    )
    x_custom_dpp_factor = fields.Float(
        string="DPP Factor",
        digits=(12, 6),
        default=1.0,
        help="Multiplier applied to the subtotal when 'DPP Method = Nilai Lain'. "
             "E.g. 11/12 ≈ 0.916667 for the PPN 11%-effective-via-12% transition.",
    )
    x_custom_dpp_category = fields.Selection(
        DPP_CATEGORY_SELECTION,
        string="DPP Category",
        help="PMK 131/2024 category — surfaces in the Coretax e-Faktur XML.",
    )

    # ------------------------------------------------------------------
    # Override the per-line tax computation to apply the DPP factor.
    # Odoo's ``_compute_amount`` returns the tax amount for a single line.
    # We multiply ``base_amount`` by the factor before delegating to super.
    # ------------------------------------------------------------------

    def _compute_amount(self, base_amount, price_unit, quantity=1.0, product=None,
                       partner=None, fixed_multiplicator=1):
        if self.x_custom_dpp_method == "nilai_lain" and self.x_custom_dpp_factor:
            base_amount = base_amount * self.x_custom_dpp_factor
        return super()._compute_amount(
            base_amount, price_unit, quantity=quantity, product=product,
            partner=partner, fixed_multiplicator=fixed_multiplicator,
        )

    @api.constrains("x_custom_dpp_method", "x_custom_dpp_factor")
    def _check_dpp_factor(self):
        for rec in self:
            if rec.x_custom_dpp_method == "nilai_lain":
                if not rec.x_custom_dpp_factor or rec.x_custom_dpp_factor <= 0:
                    raise models.ValidationError(
                        _("DPP Nilai Lain requires a positive ``dpp_factor`` (e.g. 11/12).")
                    )
