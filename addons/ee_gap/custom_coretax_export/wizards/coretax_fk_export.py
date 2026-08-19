# -*- coding: utf-8 -*-
"""Date-range e-Faktur Keluaran (FK/OF) export.

The original wizard exports one masa pajak in full, which is right for the
monthly filing but wrong for everything else — a re-export of a corrected
handful of invoices, a single customer's faktur, one sales journal. This wizard
takes an arbitrary date range plus optional partner/journal filters and hands
back the same FK/OF workbook.
"""

from __future__ import annotations

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


def _month_start(record):
    return fields.Date.context_today(record).replace(day=1)


def _month_end(record):
    return _month_start(record) + relativedelta(months=1, days=-1)


class CoretaxFkExportWizard(models.TransientModel):
    _name = "custom.coretax.fk.export.wizard"
    _inherit = "custom.coretax.fk.builder"
    _description = "Export e-Faktur Keluaran (FK/OF) by Date Range"

    date_from = fields.Date(required=True, string="Dari Tanggal", default=_month_start)
    date_to = fields.Date(required=True, string="Sampai Tanggal", default=_month_end)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        string="Perusahaan",
    )
    partner_ids = fields.Many2many(
        "res.partner",
        string="Pelanggan",
        help="Kosongkan untuk semua pelanggan. Anak perusahaan pelanggan ikut terpilih.",
    )
    journal_ids = fields.Many2many(
        "account.journal",
        string="Jurnal Penjualan",
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
        help="Kosongkan untuk semua jurnal penjualan.",
    )
    preview_count = fields.Integer(
        compute="_compute_preview_count",
        string="Faktur Terpilih",
        help="Jumlah faktur penjualan ter-posting yang akan masuk ke berkas.",
    )
    empty_reason = fields.Text(
        compute="_compute_preview_count",
        string="Kenapa kosong",
        help="Alasan filter saat ini tidak menjaring faktur apa pun.",
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_("'Dari Tanggal' tidak boleh melewati 'Sampai Tanggal'."))

    @api.depends("date_from", "date_to", "company_id", "partner_ids", "journal_ids")
    def _compute_preview_count(self):
        for wizard in self:
            # Shown before the user commits to an export, so an unsaved or
            # half-filled form must not blow up on the search.
            if not (wizard.date_from and wizard.date_to and wizard.date_from <= wizard.date_to):
                wizard.preview_count = 0
                wizard.empty_reason = False
                continue
            wizard.preview_count = self.env["account.move"].search_count(wizard._fk_domain())
            # Say why while the filters are still on screen and editable —
            # by the time the export raises, the user has already committed.
            wizard.empty_reason = "\n\n".join(wizard._empty_hints()) if not wizard.preview_count else False

    def _fk_domain(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("invoice_date", ">=", self.date_from),
            ("invoice_date", "<=", self.date_to),
        ]
        domain += self._coretax_partner_domain(self.partner_ids)
        domain += self._coretax_journal_domain(self.journal_ids)
        return domain

    def _empty_hints(self):
        self.ensure_one()
        return self._coretax_fk_empty_hints(
            self.date_from,
            self.date_to,
            self.company_id,
            partner_ids=self.partner_ids,
            journal_ids=self.journal_ids,
        )

    def _fk_moves(self):
        self.ensure_one()
        return self.env["account.move"].search(self._fk_domain(), order="invoice_date, name")

    def action_export(self):
        self.ensure_one()
        moves = self._fk_moves()
        if not moves:
            # Name the filters back: "no data" is almost always a filter that
            # was narrower than the user thought, not an empty period. The
            # company is listed first because it is the one filter the wizard
            # fills in by itself, and therefore the one the user never checks.
            applied = [
                _("perusahaan: %s", self.company_id.display_name),
                _("periode %s s/d %s", self.date_from, self.date_to),
            ]
            if self.partner_ids:
                applied.append(_("pelanggan: %s", ", ".join(self.partner_ids.mapped("name"))))
            if self.journal_ids:
                applied.append(_("jurnal: %s", ", ".join(self.journal_ids.mapped("name"))))
            hints = self._empty_hints()
            raise UserError(
                _(
                    "Tidak ada faktur penjualan ter-posting yang cocok dengan filter:\n%(filters)s\n\n%(hints)s",
                    filters="\n".join("  - %s" % item for item in applied),
                    hints="\n\n".join(hints),
                )
            )
        filename = "faktur_keluaran_%s_%s.xlsx" % (
            self.date_from.strftime("%Y%m%d"),
            self.date_to.strftime("%Y%m%d"),
        )
        return self._coretax_fk_export(moves, filename=filename)
