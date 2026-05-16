# -*- coding: utf-8 -*-
"""Account move extensions for Coretax NSFP lifecycle."""

from __future__ import annotations

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_NSFP_RE = re.compile(r"^\d{17}$")


class AccountMove(models.Model):
    _inherit = "account.move"

    # Coretax submission state (independent of accounting state)
    x_custom_coretax_status = fields.Selection(
        selection=[
            ("draft", "Draft (not submitted)"),
            ("submitted", "Submitted to Coretax"),
            ("approved", "Approved by DJP"),
            ("rejected_djp", "Rejected by DJP"),
        ],
        string="Coretax Status",
        default="draft",
        tracking=True,
        copy=False,
    )

    # NSFP assigned by DJP after approval — 17 digits:
    # 2 transaction-code + 2 status-code + 13 serial (2-digit year + 11-digit running)
    x_custom_nsfp = fields.Char(
        string="NSFP",
        size=17,
        copy=False,
        tracking=True,
        help="Nomor Seri Faktur Pajak — 17 digits assigned by DJP after Coretax "
             "approval. Format: TT + SS + YYNNNNNNNNNNN.",
    )

    x_custom_coretax_status_code = fields.Selection(
        selection=[
            ("00", "00 — Normal"),
            ("01", "01 — Pengganti 1"),
            ("02", "02 — Pengganti 2"),
            ("03", "03 — Pengganti 3"),
            ("04", "04 — Pengganti 4"),
            ("05", "05 — Pengganti 5"),
            ("06", "06 — Pengganti 6"),
            ("07", "07 — Pengganti 7"),
            ("08", "08 — Pengganti 8"),
            ("09", "09 — Pengganti 9"),
        ],
        string="Coretax Status Code",
        default="00",
        help="Faktur status code (00 normal, 01..09 = pengganti N).",
    )

    x_custom_coretax_submission_uuid = fields.Char(
        string="Coretax Submission UUID",
        copy=False,
        help="Reference returned by the DJP Coretax portal / ASPP after submission.",
    )

    x_custom_coretax_response_attach_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Coretax Response Attachment",
        copy=False,
        help="DJP response artifact (approval PDF / XML).",
    )

    @api.constrains("x_custom_nsfp")
    def _check_nsfp(self):
        for rec in self:
            if rec.x_custom_nsfp and not _NSFP_RE.match(rec.x_custom_nsfp):
                raise ValidationError(_(
                    "NSFP must be exactly 17 digits (got: %s)."
                ) % rec.x_custom_nsfp)

    @api.constrains("x_custom_coretax_status", "x_custom_nsfp")
    def _check_nsfp_required_on_approval(self):
        for rec in self:
            if rec.x_custom_coretax_status == "approved" and not rec.x_custom_nsfp:
                raise ValidationError(_(
                    "Cannot mark a move as Coretax-approved without an NSFP."
                ))
